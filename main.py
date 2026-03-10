"""
main.py — V7.4
Chef d'orchestre Xëtu — ZÉRO logique métier ici.

MIGRATIONS V7.4 depuis V7.3 :
  - FIX B2  : Proactivité hallucinée — guard strict : ligne doit venir du signalement courant
              uniquement, jamais du session_context résiduel
  - FIX B3  : Confirmation signalement moins rigide
              → _is_confirmation_implicite() étendu (vas-y, go, yep, exact, affirm…)
              → branche else : feedback utile au lieu de silence total
  - FIX B6  : send_fn passé à _dispatch → proactivité Telegram fonctionne
  - FIX B8  : Enrichissement qualitatif multi-qualités
              → extract_qualites() depuis router, toutes les qualités enregistrées
  - FIX B9  : send_fn erreur Telegram — closure capture chat_id (entier), pas user_id (string)

MIGRATIONS V7.3 depuis V7.2 :
  - SESSION 3 : Ajout adaptateur Telegram
  - FIX : send_fn passé en paramètre à tous les handlers (pas de monkey-patch)

ARCHITECTURE — Ordre de priorité strict :
    1. ABANDON             → toujours prioritaire, reset propre
    2. SESSION ACTIVE      → handler dédié, ignore intent LLM
    3. MESSAGE HYBRIDE     → multi-action (signalement + autre)
    4. INTENT LLM NORMAL   → dispatch classique
"""
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import VERIFY_TOKEN, WELCOME_MESSAGE, VALID_LINES
from services.whatsapp import parse_incoming_message
import services.whatsapp as _whatsapp_service
from services.language import detect_language
from services import whisper
from services import telegram as telegram_service
from db import queries
from agent.router import route_async, extract_qualites
from agent.normalizer import normalize
from core.context_builder import build_context
from core.security import verify_webhook_signature, validate_phone, check_rate_limit
import core.queue_manager as queue_manager
import skills.signalement as skill_signalement
import skills.question as skill_question
import skills.abonnement as skill_abonnement
import skills.escalade as skill_escalade
import skills.itineraire as skill_itineraire
from heartbeat.runner import start_heartbeat
from memory import user_memory
from core.session_manager import (
    get_context, is_abandon, reset_context, set_session
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

_MAX_MESSAGE_LENGTH = 500
_MIN_MESSAGE_LENGTH = 1


# ═══════════════════════════════════════════════════════════
# LIFESPAN
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_heartbeat()
    logger.info("🚌 Xëtu V7.4 démarré — fixes proactivité + confirmation + multi-qualités")
    yield
    logger.info("🚌 Xëtu V7.4 arrêté proprement")


app = FastAPI(title="Xëtu — Agent Transport Dakar", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://xetudashbord.pages.dev"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

from api.buses import router as buses_router
from api.leaderboard import router as leaderboard_router

app.include_router(buses_router)
app.include_router(leaderboard_router)


# ═══════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    db_ok = False
    try:
        queries.get_session("health_check_probe")
        db_ok = True
    except Exception:
        pass
    status = "ok" if db_ok else "degraded"
    return {"status": status, "service": "Xëtu", "version": "7.4", "db": db_ok}


# ═══════════════════════════════════════════════════════════
# WEBHOOK WHATSAPP
# ═══════════════════════════════════════════════════════════

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
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body_bytes = await request.body()
    signature  = request.headers.get("X-Hub-Signature-256")
    if not verify_webhook_signature(body_bytes, signature):
        raise HTTPException(status_code=403, detail="Signature invalide")

    try:
        import json
        payload = json.loads(body_bytes)
    except Exception:
        return {"status": "invalid_json"}

    msg = parse_incoming_message(payload)
    if not msg:
        return {"status": "ignored"}

    phone = msg["phone"]

    if not validate_phone(phone):
        logger.warning(f"[Webhook] Phone invalide rejeté : {phone[:20]}")
        return {"status": "invalid_phone"}

    if not check_rate_limit(phone):
        return {"status": "rate_limited"}

    text = msg.get("text")

    if msg["message_type"] == "audio":
        audio_id = msg.get("audio_id")
        if audio_id:
            text = await whisper.transcribe(audio_id)
        if not text:
            await _whatsapp_service.send_message(
                phone, "🎤 Impossible de transcrire ton message vocal. Écris-moi !"
            )
            return {"status": "audio_failed"}

    if not text:
        return {"status": "no_text"}

    await _process_message(phone, text, background_tasks)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# WEBHOOK TELEGRAM
# ═══════════════════════════════════════════════════════════

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return {"status": "invalid_json"}

    msg = telegram_service.parse_incoming_update(payload)
    if not msg:
        return {"status": "ignored"}

    user_id = msg["user_id"]   # ex: "tg_123456789"
    chat_id = msg["chat_id"]   # entier, pour répondre
    text    = msg["text"]

    if not check_rate_limit(user_id):
        return {"status": "rate_limited"}

    # FIX B9 : closure capture chat_id (entier Telegram), pas user_id (string "tg_xxx")
    # Le premier arg est ignoré — send_fn(_, msg) répond toujours au bon chat_id
    async def _send_telegram(_: str, message: str) -> bool:
        return await telegram_service.send_message(chat_id, message)

    await _process_message_telegram(user_id, text, background_tasks, _send_telegram)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════
# HELPERS — DÉTECTION
# ═══════════════════════════════════════════════════════════

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
    FIX B3 : Étendu pour couvrir les vraies réponses naturelles.
    Avant : oui/waaw/ok/exactement/parfait
    Après : + vas-y, go, yep, affirm, bien sûr, évidemment, confirme, tout à fait…
    """
    t = text.strip().lower()
    patterns = [
        # Confirmations directes
        r"^\s*(je\s+signal[e]?|signal[e]?)\s*[!.]*\s*$",
        r"^\s*(oui|ouais|yes|waaw|waaw\s+waaw)\s*[!.]*\s*$",
        r"^\s*(c['']est\s+(bon|là|ça|correct|ok)|voilà|voila)\s*[!.]*\s*$",
        r"^\s*(ok|okay|ça\s+marche|d['']accord)\s*[!.]*\s*$",
        r"^\s*(exactement|exact|c['']est\s+ça)\s*[!.]*\s*$",
        r"^\s*(parfait|super|cool)\s*[!.]*\s*$",
        # FIX B3 : patterns naturels supplémentaires
        r"^\s*(vas[- ]y|go|yep|yap)\s*[!.]*\s*$",
        r"^\s*(affirm[e]?|affirmatif)\s*[!.]*\s*$",
        r"^\s*(bien\s+sûr|bien\s+sur|évidemment|evidemment|absolument)\s*[!.]*\s*$",
        r"^\s*(confirm[e]?|je\s+confirm[e]?)\s*[!.]*\s*$",
        r"^\s*(tout\s+à\s+fait|tout\s+a\s+fait)\s*[!.]*\s*$",
        r"^\s*(carrément|carrement|clairement)\s*[!.]*\s*$",
        # Wolof
        r"^\s*(waaw\s+lool|waaw\s+bañ|ndax|diaxle)\s*[!.]*\s*$",
    ]
    return any(re.search(p, t) for p in patterns)


def _is_annulation(text: str) -> bool:
    t = text.strip().lower()
    patterns = [
        r"\bfinalement\s+(non|pas)\b",
        r"\bje\s+me\s+suis\s+tromp[eé]\b",
        r"^\s*(non|nope|nan)\s*[!.]*\s*$",
        r"\bc['']est\s+pas\s+(ça|correct|bon)\b",
        r"\bannul[e]?\b",
        r"^\s*attends?\s*[!.]*\s*$",
        r"\berreur\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _is_enrichissement_qualitatif(text: str) -> bool:
    """Vérifie si le texte contient au moins une qualité (délègue à extract_qualites)."""
    return len(extract_qualites(text)) > 0


def _detecter_signalement_dans_message(entities: dict) -> bool:
    return bool(entities.get("ligne") and entities.get("origin"))


def _detecter_multi_ligne(entities: dict) -> list[str]:
    lignes = entities.get("lignes", [])
    if isinstance(lignes, list) and len(lignes) > 1:
        seen = set()
        unique = []
        for l in lignes:
            l_upper = str(l).upper()
            if l_upper not in seen:
                seen.add(l_upper)
                unique.append(l_upper)
        return unique if len(unique) > 1 else []
    ligne = entities.get("ligne")
    return [str(ligne)] if ligne else []


def _detecter_signalement_negatif(text: str) -> bool:
    t = text.strip().lower()
    patterns = [
        r"\bplus\s+de\s+bus\b",
        r"\baucun\s+bus\b",
        r"\bpas\s+de\s+bus\b",
        r"\baucun\b.*\b(passe|vient|arrive)\b",
    ]
    return any(re.search(p, t) for p in patterns)


def _detecter_question_communautaire(text: str) -> bool:
    t = text.strip().lower()
    patterns = [
        r"\bquelqu['']un\b.*\bvu\b",
        r"\bquelqu['']un\b.*\bsait\b",
        r"\bquelqu['']un\b.*\bpass[eé]\b",
        r"\bvous\s+avez\s+vu\b",
        r"\bqui\s+a\s+vu\b",
    ]
    return any(re.search(p, t) for p in patterns)


# ═══════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL — WHATSAPP
# ═══════════════════════════════════════════════════════════

async def _process_message(phone: str, text: str, background_tasks: BackgroundTasks):
    try:
        async with queue_manager.process(phone):
            await _process_message_safe(
                phone, text, background_tasks,
                send_fn=_whatsapp_service.send_message
            )
    except Exception as e:
        logger.error(f"Erreur queue [{phone}]: {e}", exc_info=True)
        await _whatsapp_service.send_message(
            phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏"
        )


# ═══════════════════════════════════════════════════════════
# PIPELINE PRINCIPAL — TELEGRAM
# ═══════════════════════════════════════════════════════════

async def _process_message_telegram(
    user_id: str,
    text: str,
    background_tasks: BackgroundTasks,
    send_fn,
):
    try:
        async with queue_manager.process(user_id):
            await _process_message_safe(user_id, text, background_tasks, send_fn=send_fn)
    except Exception as e:
        logger.error(f"[Telegram] Erreur pipeline [{user_id}]: {e}", exc_info=True)
        # FIX B9 : send_fn est une closure — elle sait déjà à quel chat_id envoyer
        await send_fn(user_id, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


# ═══════════════════════════════════════════════════════════
# PIPELINE SAFE — PARTAGÉ WHATSAPP + TELEGRAM
# ═══════════════════════════════════════════════════════════

async def _process_message_safe(
    phone: str,
    text: str,
    background_tasks: BackgroundTasks,
    send_fn,
):
    try:
        # ── 0. PRÉ-FILTRES ────────────────────────────────
        error_msg = _check_message(text)
        if error_msg:
            await send_fn(phone, error_msg)
            return

        # ── 1. NORMALISATION ──────────────────────────────
        normalized = normalize(text)

        # ── 2. SESSION — lecture anticipée ────────────────
        session = get_context(phone)

        # ── 2.5. HISTORY — chargé AVANT route_async ───────
        _contact_pre = queries.get_or_create_contact(phone, "fr")
        _conv_pre    = queries.get_or_create_conversation(_contact_pre["id"])
        history      = queries.get_recent_messages(_conv_pre["id"])

        # ── 3. ROUTING & EXTRACTION ───────────────────────
        route_result = await route_async(
            normalized,
            history=history,
            session_context=session,
        )
        langue = route_result.lang or detect_language(text)

        est_auteur_signalement = getattr(route_result, "is_signalement_fort", False)

        # ── 4. DB — contact/conv définitifs ───────────────
        contact      = queries.get_or_create_contact(phone, langue)
        conversation = queries.get_or_create_conversation(contact["id"])
        conv_id      = conversation["id"]
        if contact["id"] != _contact_pre["id"]:
            history = queries.get_recent_messages(conv_id)

        # ── 5. PREMIER MESSAGE → accueil ──────────────────
        if not history:
            await send_fn(phone, WELCOME_MESSAGE)

        # ── 6. SAUVEGARDE message entrant ─────────────────
        queries.save_message(conv_id, "user", text, langue, route_result.intent)

        # ══════════════════════════════════════════════════
        # PRIORITÉ 1 : ABANDON
        # ══════════════════════════════════════════════════
        if route_result.intent == "abandon" or is_abandon(text):
            reset_context(phone)
            response = _reponse_abandon(langue)
            await send_fn(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "abandon")
            return

        # ══════════════════════════════════════════════════
        # PRIORITÉ 2 : SESSION ACTIVE
        # ══════════════════════════════════════════════════
        if session.etat:
            response = await _handle_session_active(
                phone=phone,
                text=text,
                langue=langue,
                session=session,
                route_result=route_result,
                contact=contact,
                conv_id=conv_id,
                history=history,
                background_tasks=background_tasks,
                send_fn=send_fn,
            )
            if response is not None:
                await send_fn(phone, response)
                queries.save_message(conv_id, "assistant", response, langue, route_result.intent)
                return

        # ══════════════════════════════════════════════════
        # PRIORITÉ 3 : MESSAGE HYBRIDE
        # ══════════════════════════════════════════════════
        if (
            route_result.intent != "signalement"
            and _detecter_signalement_dans_message(route_result.entities)
            and not _detecter_question_communautaire(text)
        ):
            await _handle_signalement_silencieux(
                phone=phone,
                entities=route_result.entities,
                langue=langue,
                background_tasks=background_tasks,
            )

        # ══════════════════════════════════════════════════
        # PRIORITÉ 3b : SIGNALEMENT DOUBLE LIGNE
        # ══════════════════════════════════════════════════
        if route_result.intent == "signalement":
            lignes = _detecter_multi_ligne(route_result.entities)
            if len(lignes) > 1:
                response = await _handle_multi_ligne(
                    phone=phone,
                    text=text,
                    langue=langue,
                    entities=route_result.entities,
                    lignes=lignes,
                    contact=contact,
                    conv_id=conv_id,
                    background_tasks=background_tasks,
                )
                await send_fn(phone, response)
                queries.save_message(conv_id, "assistant", response, langue, "signalement")

                if not est_auteur_signalement:
                    await _proposer_abonnement_si_nouveau(phone, lignes[0], langue, send_fn)
                return

        # ══════════════════════════════════════════════════
        # PRIORITÉ 4 : DISPATCH NORMAL PAR INTENT LLM
        # ══════════════════════════════════════════════════
        response = await _dispatch(
            text=text,
            intent=route_result.intent,
            contact=contact,
            langue=langue,
            conv_id=conv_id,
            history=history,
            entities=route_result.entities,
            background_tasks=background_tasks,
        )

        await send_fn(phone, response)
        queries.save_message(conv_id, "assistant", response, langue, route_result.intent)

        # ── PROACTIVITÉ ───────────────────────────────────
        # FIX B2 : guard strict — ligne UNIQUEMENT depuis entities du message courant
        # source doit être un vrai résultat de routing, jamais un résidu de session
        ligne_extraite = route_result.entities.get("ligne")
        if (
            route_result.intent == "signalement"
            and ligne_extraite
            and route_result.source in ("signalement_fort", "llm", "regex", "regex_low")
            and not est_auteur_signalement
        ):
            await _proposer_abonnement_si_nouveau(phone, ligne_extraite, langue, send_fn)

        # ── MÉMOIRE USAGER ────────────────────────────────
        contact["_last_message"] = text
        user_memory.update_after_message(
            contact=contact,
            langue=langue,
            intent=route_result.intent,
            ligne=ligne_extraite,
            arret=(
                route_result.entities.get("arret")
                or route_result.entities.get("position")
                or route_result.entities.get("origin")
            ),
        )

    except Exception as e:
        logger.error(f"Erreur pipeline [{phone}]: {e}", exc_info=True)
        await send_fn(phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


# ═══════════════════════════════════════════════════════════
# HANDLER — SESSION ACTIVE (PRIORITÉ 2)
# ═══════════════════════════════════════════════════════════

async def _handle_session_active(
    phone: str, text: str, langue: str,
    session, route_result, contact: dict,
    conv_id: str, history: list,
    background_tasks: BackgroundTasks,
    send_fn,
) -> str | None:
    intent   = route_result.intent
    entities = route_result.entities

    # ── Annulation explicite ──────────────────────────────
    if _is_annulation(text):
        reset_context(phone)
        return _reponse_annulation(langue)

    # ── État : attente_arret ──────────────────────────────
    if session.etat == "attente_arret":
        if (
            _is_confirmation_implicite(text)
            or intent == "signalement"
        ) and session.ligne and session.signalement:
            position = session.signalement.get("position", "")
            response = await skill_signalement.handle(
                message=text,
                contact=contact,
                langue=langue,
                entities={"ligne": session.ligne, "arret": position},
                background_tasks=background_tasks,
                is_signalement_fort=True,
            )
            reset_context(phone)
            return response

        return await skill_question.handle_arret_response(
            phone, text, langue, entities, history=history
        )

    # ── État : attente_origin ─────────────────────────────
    if session.etat == "attente_origin":
        return await skill_itineraire.handle_origin_response(
            phone, text, langue, entities, history=history
        )

    # ── État : post_signalement ───────────────────────────
    if session.etat == "post_signalement":
        logger.info(
            f"[Session] post_signalement — text='{text}' "
            f"enrichissement={_is_enrichissement_qualitatif(text)}"
        )
        if _is_enrichissement_qualitatif(text):
            response = await _handle_enrichissement(
                phone=phone,
                text=text,
                langue=langue,
                session=session,
            )
            reset_context(phone)
            return response
        reset_context(phone)
        return None

    # ── État : attente_confirmation_signalement (RED TEAM) ─
    if session.etat == "attente_confirmation_signalement":
        if _is_confirmation_implicite(text):
            ligne_conf = session.ligne
            arret_conf = session.signalement.get("position", "") if session.signalement else ""

            if ligne_conf and arret_conf:
                try:
                    result = queries.save_signalement(ligne_conf, arret_conf, phone)
                    if result is None:
                        reset_context(phone)
                        return f"👍 Bus {ligne_conf} à *{arret_conf}* — déjà signalé. Merci ! 🙏"

                    set_session(
                        phone,
                        etat="post_signalement",
                        ligne=ligne_conf,
                        signalement={"position": arret_conf, "ligne": ligne_conf},
                    )

                    background_tasks.add_task(
                        skill_signalement.notify_abonnes, ligne_conf, arret_conf, phone
                    )

                    logger.info(
                        f"[Confirmation] Signalement enregistré + session post_signalement "
                        f"ligne={ligne_conf} arret={arret_conf}"
                    )

                    if langue == "wolof":
                        return (
                            f"✅ Jërëjëf ! Bus {ligne_conf} ci *{arret_conf}* enregistré.\n"
                            f"Tu veux ajouter une info ? (bondé, vide, en retard…) 🙏"
                        )
                    return (
                        f"✅ Merci ! Bus {ligne_conf} à *{arret_conf}* enregistré.\n"
                        f"Tu peux ajouter : *bondé*, *vide*, *en retard*… 🙏"
                    )

                except Exception as e:
                    logger.error(f"[Confirmation] Erreur save: {e}")
                    reset_context(phone)
                    return "❌ Erreur lors de l'enregistrement. Réessaie."

            reset_context(phone)
            return "❌ Données perdues. Réessaie ton signalement. 🙏"

        elif _is_annulation(text) or text.strip().lower() in ("non", "nan", "nope"):
            reset_context(phone)
            if langue == "wolof":
                return "👍 OK, signal bi annulé."
            return "👍 OK, signalement annulé."

        else:
            # FIX B3 : feedback utile au lieu du silence total (return None)
            reset_context(phone)
            if langue == "wolof":
                return (
                    "Waxal ma ko ci kanam — envoie *Bus [numéro] ci [arrêt]* bou neex nga. 😊"
                )
            return (
                "Pas de souci ! Pour signaler un bus, envoie-moi par exemple :\n"
                "*Bus 15 à Liberté 5* 😊"
            )

    # ── État : itineraire_actif → laisser passer ──────────
    if session.etat == "itineraire_actif":
        return None

    # ── État inconnu ──────────────────────────────────────
    logger.warning(f"[Session] État inconnu '{session.etat}' pour {phone}, reset.")
    reset_context(phone)
    return None


# ═══════════════════════════════════════════════════════════
# HANDLER — SIGNALEMENT SILENCIEUX (hybride)
# ═══════════════════════════════════════════════════════════

async def _handle_signalement_silencieux(
    phone: str, entities: dict, langue: str,
    background_tasks: BackgroundTasks,
) -> None:
    ligne = str(entities["ligne"]).upper()
    arret = entities.get("arret") or entities.get("position") or entities.get("origin", "")
    logger.info(f"[Hybride] Signalement silencieux ligne={ligne} arret={arret}")
    try:
        result = queries.save_signalement(ligne=ligne, arret=arret, phone=phone)
        if result is None:
            logger.info(f"[Hybride] Doublon ignoré ligne={ligne} arret={arret}")
            return
        background_tasks.add_task(skill_signalement.notify_abonnes, ligne, arret, phone)
    except Exception as e:
        logger.error(f"[Hybride] Erreur signalement silencieux: {e}")


# ═══════════════════════════════════════════════════════════
# HANDLER — MULTI-LIGNE
# ═══════════════════════════════════════════════════════════

async def _handle_multi_ligne(
    phone: str, text: str, langue: str,
    entities: dict, lignes: list[str],
    contact: dict, conv_id: str,
    background_tasks: BackgroundTasks,
) -> str:
    arret = (
        entities.get("arret")
        or entities.get("position")
        or entities.get("origin", "")
    )
    confirmations = []

    for ligne in lignes:
        try:
            result = queries.save_signalement(
                ligne=ligne.upper(), arret=arret, phone=phone
            )
            if result is None:
                logger.info(f"[Multi-ligne] Doublon ignoré ligne={ligne}")
                continue
            background_tasks.add_task(
                skill_signalement.notify_abonnes, ligne.upper(), arret, phone
            )
            confirmations.append(f"Bus *{ligne.upper()}*")
        except Exception as e:
            logger.error(f"[Multi-ligne] Erreur ligne {ligne}: {e}")

    if not confirmations:
        return "❌ Impossible d'enregistrer les signalements. Réessaie."

    noms = " et ".join(confirmations)
    if langue == "wolof":
        return f"✅ Jëf-jël ! {noms} ci *{arret}* — Signalé pour tout le monde. 🙏"
    return f"✅ Merci ! {noms} à *{arret}* — signalés pour la communauté. 🙏"


# ═══════════════════════════════════════════════════════════
# HANDLER — ENRICHISSEMENT QUALITATIF
# ═══════════════════════════════════════════════════════════

async def _handle_enrichissement(
    phone: str, text: str, langue: str, session
) -> str:
    """
    FIX B8 : Enregistre TOUTES les qualités présentes dans le message.
    "bondé et en retard" → les deux qualités sont enregistrées en DB.
    """
    ligne    = session.ligne or ""
    position = session.signalement.get("position", "") if session.signalement else ""

    qualites = extract_qualites(text)
    if not qualites:
        qualites = ["info"]

    for qualite in qualites:
        try:
            queries.enrichir_signalement(
                ligne=ligne.upper(), arret=position, qualite=qualite, phone=phone
            )
            logger.info(f"[Enrichissement] ligne={ligne} arret={position} qualite={qualite}")
        except Exception as e:
            logger.error(f"[Enrichissement] Erreur qualite={qualite}: {e}")

    # Confirmation adaptée à la qualité principale
    q = qualites[0]

    if q == "déjà parti":
        if langue == "wolof":
            return f"👍 Compris — Bus *{ligne}* dem na ci *{position}*. Info enregistrée."
        return f"👍 Noté — Bus *{ligne}* déjà parti de *{position}*. Info utile pour la communauté !"
    if q == "bondé":
        if langue == "wolof":
            return f"👍 Bus *{ligne}* ci *{position}* — dëkk na ! Signalé. 🚌"
        return f"👍 Bus *{ligne}* à *{position}* — bondé ! Info enregistrée. 🚌"
    if q == "vide":
        return f"👍 Bus *{ligne}* à *{position}* — peu de monde. Noté !"
    if q == "repart maintenant":
        return f"🔄 Re-signalement noté — Bus *{ligne}* repart de *{position}*. Merci !"
    if len(qualites) > 1:
        qualites_str = " et ".join(qualites)
        return f"👍 Bus *{ligne}* à *{position}* — {qualites_str}. Noté pour la communauté ! 🙏"

    return f"👍 Info notée pour le Bus *{ligne}* à *{position}*. Merci ! 🙏"


# ═══════════════════════════════════════════════════════════
# DISPATCH NORMAL (PRIORITÉ 4)
# ═══════════════════════════════════════════════════════════

async def _dispatch(
    text: str, intent: str, contact: dict,
    langue: str, conv_id: str, history: list,
    entities: dict, background_tasks: BackgroundTasks,
) -> str:

    if intent == "signalement":
        return await skill_signalement.handle(
            text, contact, langue, entities, background_tasks
        )

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
        from agent.llm_brain import generate_response
        ctx = build_context(
            message=text,
            intent="out_of_scope",
            contact=contact,
            history=history,
        )
        return await generate_response(ctx, langue, history)


# ═══════════════════════════════════════════════════════════
# HELPERS — RÉPONSES
# ═══════════════════════════════════════════════════════════

def _reponse_abandon(langue: str) -> str:
    if langue == "wolof":
        return "Waaw, sëde ko. 👍 Wax ma dara buy soxor."
    return "OK, pas de souci. 👍 Reviens quand tu veux."


def _reponse_annulation(langue: str) -> str:
    if langue == "wolof":
        return "Waaw, dal naa ko. 👍 Fii bok, wax ma ñu mën a def."
    return "Annulé ! 👍 Dis-moi ce que tu veux faire."


# ═══════════════════════════════════════════════════════════
# PROACTIVITÉ
# ═══════════════════════════════════════════════════════════

async def _proposer_abonnement_si_nouveau(phone: str, ligne: str, langue: str, send_fn):
    """
    Propose un abonnement uniquement si l'usager n'est pas encore abonné.
    FIX B2 : Appelé UNIQUEMENT si ligne vient du signalement courant (guard dans pipeline).
    N'est JAMAIS appelé si est_auteur_signalement == True.
    """
    try:
        abonnes     = queries.get_abonnes(ligne)
        deja_abonne = any(a["phone"] == phone for a in abonnes)
        if not deja_abonne:
            if langue == "wolof":
                suggestion = (
                    f"💡 Bëgg nga ma la wéer bu ñu signalé Bus *{ligne}* ?\n"
                    f"Yëgël : *Préviens-moi pour le Bus {ligne}*"
                )
            else:
                suggestion = (
                    f"💡 Tu veux être alerté dès que le Bus *{ligne}* est signalé ?\n"
                    f"Envoie : *Préviens-moi pour le Bus {ligne}*"
                )
            await send_fn(phone, suggestion)
    except Exception as e:
        logger.error(f"[Proactivité] Erreur suggestion abonnement: {e}")