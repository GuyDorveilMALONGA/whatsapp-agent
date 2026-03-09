"""
main.py — V5.1
Chef d'orchestre Xëtu — ZÉRO logique métier ici.

V5.1 :
  + route_async remonté en étape 2 (avant session et DB)
  + langue depuis route_result.lang avec fallback detect_language
  + entities propagées dans _dispatch
  + extract() supprimé des étapes 12 et 14
  + handle_origin_response + handle_arret_response reçoivent entities
  FIX : "je veux me rendre à X" classifié itineraire (pas question)
  FIX : TypeError handle() missing 'entities' définitivement résolu
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


# ── Startup ───────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    start_heartbeat()
    logger.info("🚌 Xëtu V5.1 démarré")


# ── Health check ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Xëtu", "version": "5.1"}


# ── Webhook Meta — vérification ───────────────────────────

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


# ── Webhook Meta — messages entrants ─────────────────────

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


# ── Pré-filtres ───────────────────────────────────────────

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


# ── Pipeline principal ────────────────────────────────────

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

        # ── 2. ROUTING & EXTRACTION ───────────────────────
        # Remonté en étape 2 : LLM extrait intent + langue + entities
        # en une seule passe AVANT toute autre logique.
        # FIX : "je veux me rendre à X" → itineraire (pas question)
        route_result = await route_async(normalized, history=None)
        entities = route_result.entities if hasattr(route_result, "entities") else {}
        entities = entities or {}

        # ── 3. LANGUE ─────────────────────────────────────
        # Priorité LLM → fallback règles
        langue = route_result.lang or detect_language(text)

        # ── 4. SESSION — lecture unique ───────────────────
        # Règle absolue : get_context appelé UNE SEULE FOIS.
        session = get_context(phone)

        # ── 5. ABANDON DE FLOW ────────────────────────────
        if session.etat and is_abandon(text):
            reset_context(phone)
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            queries.save_message(conv_id, "user", text, langue, "abandon")
            response = (
                "OK, on laisse tomber. 👍 Dis-moi si tu as besoin d'autre chose."
                if langue != "wolof" else
                "Waaw, sëde ko. 👍 Wax ma dara buy soxor."
            )
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "abandon")
            return

        # ── 6. FLOW MULTI-TOUR ────────────────────────────
        # entities passées pour récupérer no_transfer_preference
        # et l'arrêt si le LLM l'a extrait du message court.
        from skills.question import handle_arret_response
        from skills.itineraire import handle_origin_response

        if session.etat == "attente_arret":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            response = await handle_arret_response(phone, text, langue, entities)
            queries.save_message(conv_id, "user",      text,     langue, "question")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "question")
            return

        if session.etat == "attente_origin":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            response = await handle_origin_response(phone, text, langue, entities)
            queries.save_message(conv_id, "user",      text,     langue, "itineraire")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "itineraire")
            return

        # ── 7. DB — seulement maintenant ──────────────────
        contact      = queries.get_or_create_contact(phone, langue)
        conversation = queries.get_or_create_conversation(contact["id"])
        conv_id      = conversation["id"]
        history      = queries.get_recent_messages(conv_id)

        # ── 8. PREMIER MESSAGE → accueil ──────────────────
        if not history:
            await send_message(phone, WELCOME_MESSAGE)

        # ── 9. SAUVEGARDE message entrant ─────────────────
        queries.save_message(conv_id, "user", text, langue, route_result.intent)

        # ── 10. DISPATCH ──────────────────────────────────
        response = await _dispatch(
            text=text,
            intent=route_result.intent,
            contact=contact,
            langue=langue,
            conv_id=conv_id,
            history=history,
            entities=entities,
        )

        # ── 11. ENVOI ─────────────────────────────────────
        await send_message(phone, response)

        # ── 12. PROACTIVITÉ ───────────────────────────────
        # Lecture depuis entities LLM — plus d'appel extract()
        ligne_extraite = entities.get("ligne")
        if route_result.intent == "signalement" and ligne_extraite:
            await _proposer_abonnement_si_nouveau(phone, ligne_extraite, langue)

        # ── 13. SAUVEGARDE réponse ────────────────────────
        queries.save_message(conv_id, "assistant", response, langue, route_result.intent)

        # ── 14. MÉMOIRE USAGER ────────────────────────────
        contact["_last_message"] = text
        user_memory.update_after_message(
            contact=contact,
            langue=langue,
            intent=route_result.intent,
            ligne=ligne_extraite,
            arret=(
                entities.get("origin")
                or entities.get("destination")
            ),
        )

    except Exception as e:
        logger.error(f"Erreur pipeline [{phone}]: {e}", exc_info=True)
        await send_message(phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


# ── Dispatch ──────────────────────────────────────────────

async def _dispatch(text: str, intent: str, contact: dict,
                    langue: str, conv_id: str, history: list,
                    entities: dict) -> str:
    if intent == "signalement":
        return await skill_signalement.handle(text, contact, langue, entities)
    elif intent == "question":
        return await skill_question.handle(text, contact, langue, history, entities)
    elif intent == "liste_arrets":
        return await skill_question.handle_liste_arrets(text, contact, langue, entities)
    elif intent == "abonnement":
        return await skill_abonnement.handle(text, contact, langue, entities)
    elif intent == "escalade":
        return await skill_escalade.handle(text, contact, langue, conv_id)
    elif intent == "itineraire":
        return await skill_itineraire.handle(text, contact, langue, entities)
    else:
        from agent.llm_brain import generate_response
        ctx = build_context(
            message=text,
            intent="out_of_scope",
            contact=contact,
            history=history,
        )
        return await generate_response(ctx, langue, history)


# ── Proactivité ───────────────────────────────────────────

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