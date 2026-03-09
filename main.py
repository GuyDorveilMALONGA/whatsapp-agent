"""
main.py — V5.6 (LLM-Native)
Chef d'orchestre Xëtu — ZÉRO logique métier ici.

FIX V5.6 :
  1. Bug "Je signale" avec session attente_arret :
     Quand session.etat == "attente_arret" ET intent == "signalement"
     → l'usager confirme implicitement son arrêt avec "Je signale".
     On enregistre le signalement avec session.ligne + session.signalement["position"]
     sans redemander d'informations déjà connues.

  2. Bug "Bus 8 en route pour jet d'eau" — messages hybrides :
     Détection AVANT le dispatch : si le message contient un signalement
     (ligne + position) ET une destination, on enregistre le signalement
     d'abord, puis on continue le flow normal (itinéraire).
     L'usager reçoit les deux : confirmation signalement + calcul itinéraire.

  3. Bug "Je signale" seul sans session :
     Si intent == "signalement" mais entities vides ET session active avec
     ligne + position → utiliser le contexte de session pour enregistrer.

FIX V5.5 :
  is_abandon_regex sans condition session.etat
  Filet défensif dans _dispatch / out_of_scope

FIX V5.4 :
  intent "alternatives_itineraire" → skill_itineraire.handle_alternatives()

FIX V5.3 :
  history chargé à l'étape 2.5 (avant route_async).

FIX V5.2 :
  session déplacée à l'étape 2 → fix UnboundLocalError
  abandon géré depuis intent LLM ET is_abandon()
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import VERIFY_TOKEN, WELCOME_MESSAGE
from services.whatsapp import parse_incoming_message, send_message
from services.language import detect_language
from services import whisper
from db import queries
from agent.router import route_async
from agent.normalizer import normalize
from core.context_builder import build_context
import core.queue_manager as queue_manager
import skills.signalement as skill_signalement
import skills.question as skill_question
import skills.abonnement as skill_abonnement
import skills.escalade as skill_escalade
import skills.itineraire as skill_itineraire
from heartbeat.runner import start_heartbeat
from memory import user_memory
from core.session_manager import (
    get_context, is_abandon, reset_context
)

from api.buses import router as buses_router
from api.leaderboard import router as leaderboard_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Xëtu — Agent Transport Dakar")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(buses_router)
app.include_router(leaderboard_router)

_MAX_MESSAGE_LENGTH = 500
_MIN_MESSAGE_LENGTH = 1


@app.on_event("startup")
async def startup():
    start_heartbeat()
    logger.info("🚌 Xëtu V5.6 démarré — Architecture LLM-Native")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Xëtu", "version": "5.6"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook Meta vérifié")
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token invalide")


@app.post("/webhook")
async def receive_message(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {"status": "invalid_json"}

    msg = parse_incoming_message(payload)
    if not msg:
        return {"status": "ignored"}

    phone = msg["phone"]
    text  = msg.get("text")

    if msg["message_type"] == "audio":
        audio_id = msg.get("audio_id")
        if audio_id:
            text = await whisper.transcribe(audio_id)
        if not text:
            await send_message(phone, "🎤 Impossible de transcrire ton message vocal. Écris-moi !")
            return {"status": "audio_failed"}

    if not text:
        return {"status": "no_text"}

    await _process_message(phone, text)
    return {"status": "ok"}


def _check_message(text: str) -> str | None:
    stripped = text.strip()
    if len(stripped) < _MIN_MESSAGE_LENGTH:
        return None
    if len(stripped) > _MAX_MESSAGE_LENGTH:
        return (
            "⚠️ Message trop long. Envoie-moi une courte phrase :\n"
            "• *Bus 15 à Liberté 5*\n"
            "• *Bus 15 est où ?*"
        )
    if len(stripped) > 10:
        alphanum = sum(1 for c in stripped if c.isalnum())
        if alphanum / len(stripped) < 0.3:
            return None
    return None


def _is_confirmation_implicite(text: str) -> bool:
    """
    Détecte "Je signale", "c'est bon", "voilà", "c'est là", "oui"
    comme confirmations implicites dans un flow multi-tour.
    NE PAS utiliser hors contexte session active.
    """
    import re
    t = text.strip().lower()
    patterns = [
        r"^\s*(je\s+signal[e]?|signal[e]?)\s*[!.]*\s*$",
        r"^\s*(oui|ouais|yes|waaw|waaw\s+waaw)\s*[!.]*\s*$",
        r"^\s*(c['']est\s+(bon|là|ça|correct|ok)|voilà|voila)\s*[!.]*\s*$",
        r"^\s*(ok|okay|ça\s+marche|d['']accord)\s*[!.]*\s*$",
        r"^\s*(exactement|exact|c['']est\s+ça)\s*[!.]*\s*$",
    ]
    return any(re.search(p, t) for p in patterns)


def _detecter_signalement_dans_message(entities: dict) -> bool:
    """
    Retourne True si le message contient les éléments d'un signalement :
    ligne + position (origin).
    Utilisé pour détecter les messages hybrides (signalement + itinéraire).
    """
    return bool(entities.get("ligne") and entities.get("origin"))


async def _process_message(phone: str, text: str):
    try:
        async with queue_manager.process(phone):
            await _process_message_safe(phone, text)
    except Exception as e:
        logger.error(f"Erreur queue [{phone}]: {e}", exc_info=True)
        await send_message(phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


async def _process_message_safe(phone: str, text: str):
    try:
        # ── 0. PRÉ-FILTRES ────────────────────────────────
        error_msg = _check_message(text)
        if error_msg:
            await send_message(phone, error_msg)
            return

        # ── 1. NORMALISATION ──────────────────────────────
        normalized = normalize(text)

        # ── 2. SESSION — lecture anticipée ────────────────
        session = get_context(phone)

        # ── 2.5 HISTORY — chargé AVANT route_async ────────
        _contact_pre  = queries.get_or_create_contact(phone, "fr")
        _conv_pre     = queries.get_or_create_conversation(_contact_pre["id"])
        history       = queries.get_recent_messages(_conv_pre["id"])

        # ── 3. ROUTING & EXTRACTION ───────────────────────
        route_result = await route_async(
            normalized,
            history=history,
            session_context=session
        )

        # ── 4. LANGUE ─────────────────────────────────────
        langue = route_result.lang or detect_language(text)

        # ── 5. ABANDON ────────────────────────────────────
        is_abandon_llm   = (route_result.intent == "abandon")
        is_abandon_regex = is_abandon(text)

        if is_abandon_llm or is_abandon_regex:
            reset_context(phone)
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            queries.save_message(conv_id, "user", text, langue, "abandon")
            response = (
                "OK, pas de souci. 👍 Reviens quand tu veux."
                if langue != "wolof" else
                "Waaw, sëde ko. 👍 Wax ma dara buy soxor."
            )
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "abandon")
            return

        # ── 6. FLOW MULTI-TOUR ────────────────────────────

        if session.etat == "attente_arret":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]

            # FIX V5.6 — Bug "Je signale"
            # L'usager confirme implicitement son arrêt OU envoie intent=signalement
            # dans un flow attente_arret → on a déjà ligne + position dans la session.
            # On enregistre le signalement directement sans redemander d'info.
            if (
                _is_confirmation_implicite(text)
                or route_result.intent == "signalement"
            ) and session.ligne and session.signalement:
                position = session.signalement.get("position", "")
                response = await skill_signalement.handle(
                    message=text,
                    contact=contact,
                    langue=langue,
                    entities={
                        "ligne": session.ligne,
                        "origin": position,
                    }
                )
                reset_context(phone)
                queries.save_message(conv_id, "user",      text,     langue, "signalement")
                await send_message(phone, response)
                queries.save_message(conv_id, "assistant", response, langue, "signalement")
                return

            # Réponse normale à la question d'arrêt
            response = await skill_question.handle_arret_response(
                phone, text, langue, route_result.entities, history=history
            )
            queries.save_message(conv_id, "user",      text,     langue, "question")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "question")
            return

        if session.etat == "attente_origin":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            response = await skill_itineraire.handle_origin_response(
                phone, text, langue, route_result.entities, history=history
            )
            queries.save_message(conv_id, "user",      text,     langue, "itineraire")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "itineraire")
            return

        # ── 7. DB — contact/conv définitifs ───────────────
        contact      = queries.get_or_create_contact(phone, langue)
        conversation = queries.get_or_create_conversation(contact["id"])
        conv_id      = conversation["id"]
        if contact["id"] != _contact_pre["id"]:
            history = queries.get_recent_messages(conv_id)

        # ── 8. PREMIER MESSAGE → accueil ──────────────────
        if not history:
            await send_message(phone, WELCOME_MESSAGE)

        # ── 9. SAUVEGARDE message entrant ─────────────────
        queries.save_message(conv_id, "user", text, langue, route_result.intent)

        # ── 10. MESSAGES HYBRIDES — signalement + autre intent ──
        # FIX V5.6 — Bug "Bus 8 en route pour jet d'eau"
        # Le message contient un signalement (ligne + position) ET une destination.
        # Le router a choisi un seul intent (itinéraire ou signalement).
        # On enregistre le signalement EN PREMIER, silencieusement,
        # puis on continue le flow normal avec l'intent choisi.
        #
        # Cas détectés :
        #   "Bus 8 en route pour Jet D'Eau"  → intent=itineraire, MAIS ligne+origin présents
        #   "J'ai vu le 6 à Colobane, comment aller à Sandaga ?" → idem
        #   "Bus 8 à Yoff Village"  → intent=signalement normal, pas hybride
        if (
            route_result.intent != "signalement"
            and _detecter_signalement_dans_message(route_result.entities)
        ):
            logger.info(
                f"[V5.6] Message hybride détecté — "
                f"signalement ligne={route_result.entities['ligne']} "
                f"pos={route_result.entities['origin']} enregistré silencieusement"
            )
            try:
                queries.save_signalement(
                    ligne=str(route_result.entities["ligne"]).upper(),
                    arret=route_result.entities["origin"],
                    phone=phone,
                )
                # Notifier les abonnés en arrière-plan
                import asyncio
                asyncio.create_task(
                    skill_signalement._notify_abonnes(
                        str(route_result.entities["ligne"]).upper(),
                        route_result.entities["origin"],
                        phone,
                    )
                )
            except Exception as e:
                logger.error(f"[V5.6] Erreur signalement hybride: {e}")

        # ── 11. DISPATCH ──────────────────────────────────
        response = await _dispatch(
            text=text,
            intent=route_result.intent,
            contact=contact,
            langue=langue,
            conv_id=conv_id,
            history=history,
            entities=route_result.entities,
        )

        # ── 12. ENVOI ─────────────────────────────────────
        await send_message(phone, response)

        # ── 13. PROACTIVITÉ ───────────────────────────────
        ligne_extraite = route_result.entities.get("ligne")
        if route_result.intent == "signalement" and ligne_extraite:
            await _proposer_abonnement_si_nouveau(phone, ligne_extraite, langue)

        # ── 14. SAUVEGARDE réponse ────────────────────────
        queries.save_message(conv_id, "assistant", response, langue, route_result.intent)

        # ── 15. MÉMOIRE USAGER ────────────────────────────
        contact["_last_message"] = text
        user_memory.update_after_message(
            contact=contact,
            langue=langue,
            intent=route_result.intent,
            ligne=ligne_extraite,
            arret=route_result.entities.get("origin") or route_result.entities.get("destination"),
        )

    except Exception as e:
        logger.error(f"Erreur pipeline [{phone}]: {e}", exc_info=True)
        await send_message(phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


async def _dispatch(text: str, intent: str, contact: dict,
                    langue: str, conv_id: str, history: list,
                    entities: dict) -> str:

    if intent == "signalement":
        return await skill_signalement.handle(text, contact, langue, entities)
    elif intent == "question":
        return await skill_question.handle(text, contact, langue, history, entities)
    elif intent == "liste_arrets":
        return await skill_question.handle_liste_arrets(text, contact, langue, entities, history)
    elif intent == "abonnement":
        return await skill_abonnement.handle(text, contact, langue, entities)
    elif intent == "escalade":
        return await skill_escalade.handle(text, contact, langue, conv_id)
    elif intent == "itineraire":
        return await skill_itineraire.handle(text, contact, langue, entities)
    elif intent == "alternatives_itineraire":
        return await skill_itineraire.handle_alternatives(
            contact["phone"], langue, history
        )
    else:
        if is_abandon(text):
            reset_context(contact["phone"])
            return (
                "OK, pas de souci. 👍 Reviens quand tu veux."
                if langue != "wolof" else
                "Waaw, sëde ko. 👍 Wax ma dara buy soxor."
            )

        from agent.llm_brain import generate_response
        ctx = build_context(
            message=text,
            intent="out_of_scope",
            contact=contact,
            history=history,
        )
        return await generate_response(ctx, langue, history)


async def _proposer_abonnement_si_nouveau(phone: str, ligne: str, langue: str):
    try:
        abonnes     = queries.get_abonnes(ligne)
        deja_abonne = any(a["phone"] == phone for a in abonnes)
        if not deja_abonne:
            if langue == "wolof":
                suggestion = (
                    f"💡 Bëgg nga ma la wéer bu ñu signalé Bus {ligne} ?\n"
                    f"Yëgël : *Préviens-moi pour le Bus {ligne}*"
                )
            else:
                suggestion = (
                    f"💡 Tu veux être alerté dès que le Bus *{ligne}* est signalé ?\n"
                    f"Envoie : *Préviens-moi pour le Bus {ligne}*"
                )
            await send_message(phone, suggestion)
    except Exception as e:
        logger.error(f"[Proactivité] Erreur suggestion abonnement: {e}")