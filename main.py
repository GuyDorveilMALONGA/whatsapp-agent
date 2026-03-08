"""
main.py — V3
Chef d'orchestre Sëtu — ZÉRO logique métier ici.
Reçoit → filtre → délègue → répond.

Cas tordus gérés :
- Session perdue au redémarrage Railway → Supabase + fallback mémoire
- "Je suis à liberté 5" pendant un flow → intercepté avant le router
- "laisse tomber" pendant un flow → abandon propre + reset session
- Spam / message vide / trop long → filtré avant le pipeline
- Injection prompt → neutralisée par normalizer
- Question d'identité ("tu es ChatGPT ?") → réponse Sëtu directe
- Supabase timeout sur session → fallback mémoire silencieux
"""
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse

from config.settings import VERIFY_TOKEN
from services.whatsapp import parse_incoming_message, send_message
from services.language import detect_language
from services import whisper
from db import queries
from agent.router import route_async
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
    is_waiting_for_arret, is_waiting_for_origin,
    is_in_flow, is_abandon, reset_context
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sëtu — Agent Transport Dakar")

# Limites de sécurité
_MAX_MESSAGE_LENGTH = 500   # caractères
_MIN_MESSAGE_LENGTH = 1


# ── Startup ───────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    start_heartbeat()
    logger.info("🚌 Sëtu V3 démarré")


# ── Health check ──────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Sëtu", "version": "3.0"}


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

    # Audio → transcription Whisper
    if msg["message_type"] == "audio":
        audio_id = msg.get("audio_id")
        if audio_id:
            text = await whisper.transcribe(audio_id)
        if not text:
            await send_message(phone, "🎤 Impossible de transcrire le message vocal. Écris-moi !")
            return {"status": "audio_failed"}

    if not text:
        return {"status": "no_text"}

    await _process_message(phone, text)
    return {"status": "ok"}


# ── Pré-filtres ───────────────────────────────────────────

def _check_message(text: str) -> str | None:
    """
    Vérifie le message avant tout traitement.
    Retourne un message d'erreur à envoyer, ou None si ok.

    Cas filtrés :
    - Trop court (vide, espace, caractère isolé)
    - Trop long (probable copier-coller, spam)
    - Gibberish pur (aucune lettre ou chiffre)
    """
    stripped = text.strip()

    # Vide ou trop court
    if len(stripped) < _MIN_MESSAGE_LENGTH:
        return None  # On ignore silencieusement

    # Trop long → probable spam ou copier-coller
    if len(stripped) > _MAX_MESSAGE_LENGTH:
        return (
            "⚠️ Message trop long. Envoie-moi une courte phrase :\n"
            "• *Bus 15 à Liberté 5*\n"
            "• *Bus 15 est où ?*"
        )

    # Gibberish : moins de 30% de caractères alphanumériques dans les messages > 10 chars
    if len(stripped) > 10:
        alphanum = sum(1 for c in stripped if c.isalnum())
        ratio = alphanum / len(stripped)
        if ratio < 0.3:
            return None  # Ignore silencieusement (emoji spam, etc.)

    return None  # Message valide


def _get_identity_response(langue: str) -> str:
    """Réponse quand l'usager demande qui est Sëtu."""
    if langue == "wolof":
        return (
            "Maa ngi tudd *Sëtu* 🚌\n"
            "Maa ngi jëfandikoo ak bus Dem Dikk ci Dakar.\n"
            "Duma ChatGPT, duma robot — maa ngi def ak communauté bi."
        )
    return (
        "Je suis *Sëtu* 🚌, l'assistant des bus Dem Dikk à Dakar.\n"
        "Je ne suis pas ChatGPT — je suis spécialisé dans le réseau de bus de ta ville.\n"
        "Tu peux signaler un bus, demander sa position ou calculer un itinéraire."
    )


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

        # ── 1. LANGUE ─────────────────────────────────────
        langue = detect_language(text)

        # ── 2. CONTEXTE DB ────────────────────────────────
        contact      = queries.get_or_create_contact(phone, langue)
        conversation = queries.get_or_create_conversation(contact["id"])
        conv_id      = conversation["id"]
        history      = queries.get_recent_messages(conv_id)

        # ── 3. ABANDON DE FLOW ────────────────────────────
        # Vérifié en premier : "laisse tomber", "annule", "stop"
        # → reset propre de la session, pas de routage
        if is_in_flow(phone) and is_abandon(text):
            reset_context(phone)
            queries.save_message(conv_id, "user", text, langue, "abandon")
            response = (
                "OK, on laisse tomber. 👍 Tu peux m'envoyer autre chose quand tu veux."
                if langue != "wolof" else
                "Waaw, sëde ko. 👍 Wax ma dara buy soxor."
            )
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "abandon")
            return

        # ── 4. FLOW MULTI-TOUR ────────────────────────────
        # Intercepté AVANT le router — jamais vu par le scoring regex
        from skills.question import handle_arret_response
        from skills.itineraire import handle_origin_response

        # Cas A : Sëtu attend l'arrêt de l'usager (flow question)
        if is_waiting_for_arret(phone):
            response = await handle_arret_response(phone, text, langue)
            queries.save_message(conv_id, "user",      text,     langue, "question")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "question")
            return

        # Cas B : Sëtu attend l'arrêt de départ (flow itinéraire)
        if is_waiting_for_origin(phone):
            response = await handle_origin_response(phone, text, langue)
            queries.save_message(conv_id, "user",      text,     langue, "itineraire")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "itineraire")
            return

        # ── 5. ROUTING ────────────────────────────────────
        route_result = await route_async(text, history)

        # Réponse identité directe (source="identity")
        if route_result.source == "identity":
            response = _get_identity_response(langue)
            queries.save_message(conv_id, "user",      text,     langue, "out_of_scope")
            await send_message(phone, response)
            queries.save_message(conv_id, "assistant", response, langue, "out_of_scope")
            return

        # ── 6. SAUVEGARDE message entrant ─────────────────
        queries.save_message(conv_id, "user", text, langue, route_result.intent)

        # ── 7. DISPATCH ───────────────────────────────────
        response = await _dispatch(
            text=text,
            intent=route_result.intent,
            contact=contact,
            langue=langue,
            conv_id=conv_id,
            history=history,
        )

        # ── 8. ENVOI ──────────────────────────────────────
        await send_message(phone, response)

        # ── 9. PROACTIVITÉ ────────────────────────────────
        extracted = extract(text)
        if route_result.intent == "signalement" and extracted.ligne:
            await _proposer_abonnement_si_nouveau(phone, extracted.ligne, langue)

        # ── 10. SAUVEGARDE réponse ────────────────────────
        queries.save_message(conv_id, "assistant", response, langue, route_result.intent)

        # ── 11. MÉMOIRE USAGER ────────────────────────────
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

    else:  # out_of_scope
        if langue == "wolof":
            return (
                "Maa ngi seetlu bus Dem Dikk rekk. "
                "Wax ma position bus bou ngelaw, "
                "walla tappaliku ci ligne bi. 🚌"
            )
        return (
            "Je suis spécialisé dans les bus Dem Dikk de Dakar. 🚌\n"
            "Tu peux :\n"
            "• Signaler un bus : *Bus 15 à Liberté 5*\n"
            "• Demander sa position : *Bus 15 est où ?*\n"
            "• Itinéraire : *Comment aller de Yoff à Sandaga ?*\n"
            "• T'abonner : *Préviens-moi pour le Bus 15*"
        )


# ── Proactivité ───────────────────────────────────────────

async def _proposer_abonnement_si_nouveau(phone: str, ligne: str, langue: str):
    try:
        abonnes     = queries.get_abonnes(ligne)
        deja_abonne = any(a["phone"] == phone for a in abonnes)
        if not deja_abonne:
            if langue == "wolof":
                suggestion = (
                    f"💡 Bëgg nga ma la wéer bu ñu signalé Bus {ligne} ? "
                    f"Yëgël : *Préviens-moi pour le Bus {ligne}*"
                )
            else:
                suggestion = (
                    f"💡 Tu veux être alerté automatiquement dès que le Bus *{ligne}* "
                    f"est signalé ? Envoie : *Préviens-moi pour le Bus {ligne}*"
                )
            await send_message(phone, suggestion)
    except Exception as e:
        logger.error(f"[Proactivité] Erreur suggestion abonnement: {e}")