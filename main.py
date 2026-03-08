"""
main.py — V4.0
Chef d'orchestre Xëtu — ZÉRO logique métier ici.

V4.0 : + CORS + /api/buses + /api/leaderboard
FIX #2 : Routing avant DB → normalize → route → DB (~30ms gagnés)
"""
import re
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
from agent.extractor import extract
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

# ── Nouveaux routers API (V4) ─────────────────────────────
from api.buses import router as buses_router
from api.leaderboard import router as leaderboard_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Xëtu — Agent Transport Dakar")

# ── CORS (V4) — permet au dashboard public d'appeler l'API ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Restreindre à ton domaine en prod
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Enregistrement des routers API (V4) ──────────────────
app.include_router(buses_router)
app.include_router(leaderboard_router)

_MAX_MESSAGE_LENGTH = 500
_MIN_MESSAGE_LENGTH = 1


# ── Startup ───────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    start_heartbeat()
    logger.info("🚌 Xëtu V4.0 démarré")


# ── Health check ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Xëtu", "version": "4.0"}


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

        # ── 2. LANGUE ─────────────────────────────────────
        langue = detect_language(text)

        # ── 3. SESSION — lecture (légère, Supabase) ───────
        session = get_context(phone)

        # ── 4. ABANDON DE FLOW ────────────────────────────
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

        # ── 5. FLOW MULTI-TOUR ────────────────────────────
        from skills.question import handle_arret_response
        from skills.itineraire import handle_origin_response

        if session.etat == "attente_arret":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            response = await handle_arret_response(phone, text, langue)
            queries.save_message(conv_id, "user",      text,     langue, "question")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "question")
            return

        if session.etat == "attente_origin":
            contact      = queries.get_or_create_contact(phone, langue)
            conversation = queries.get_or_create_conversation(contact["id"])
            conv_id      = conversation["id"]
            response = await handle_origin_response(phone, text, langue)
            queries.save_message(conv_id, "user",      text,     langue, "itineraire")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "itineraire")
            return

        # ── 6. ROUTING (AVANT DB) ─────────────────────────
        route_result = await route_async(normalized, history=None)

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
        )

        # ── 11. ENVOI ─────────────────────────────────────
        await send_message(phone, response)

        # ── 12. PROACTIVITÉ ───────────────────────────────
        extracted = extract(text)
        if route_result.intent == "signalement" and extracted.ligne:
            await _proposer_abonnement_si_nouveau(phone, extracted.ligne, langue)

        # ── 13. SAUVEGARDE réponse ────────────────────────
        queries.save_message(conv_id, "assistant", response, langue, route_result.intent)

        # ── 14. MÉMOIRE USAGER ────────────────────────────
        contact["_last_message"] = text
        user_memory.update_after_message(
            contact=contact,
            langue=langue,
            intent=route_result.intent,
            ligne=extracted.ligne,
            arret=extracted.arret,
        )

    except Exception as e:
        logger.error(f"Erreur pipeline [{phone}]: {e}", exc_info=True)
        await send_message(phone, "Une erreur s'est produite. Réessaie dans un moment. 🙏")


# ── Dispatch ──────────────────────────────────────────────

async def _dispatch(text: str, intent: str, contact: dict,
                    langue: str, conv_id: str, history: list) -> str:

    if intent == "signalement":
        return await skill_signalement.handle(text, contact, langue)
    elif intent == "question":
        return await skill_question.handle(text, contact, langue, history)
    elif intent == "liste_arrets":
        return await skill_question.handle_liste_arrets(text, contact, langue)
    elif intent == "abonnement":
        return await skill_abonnement.handle(text, contact, langue)
    elif intent == "escalade":
        return await skill_escalade.handle(text, contact, langue, conv_id)
    elif intent == "itineraire":
        return await skill_itineraire.handle(text, contact, langue)
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