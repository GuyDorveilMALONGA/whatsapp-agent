from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os

load_dotenv()

from services.whatsapp import send_message, download_media
from services.whisper import transcribe_audio
from services.language import detect_language
from agents.router import classify_intent, should_escalate
from agents.responder import generate_response
from agents.extractor import extract_signalement, extract_abonnement
from rag.retriever import hybrid_search, format_context, search_signalements_recents, format_signalements
from db.context import (
    get_or_create_contact,
    get_or_create_conversation,
    get_recent_messages,
    save_message,
    update_contact_language,
    escalate_conversation,
    save_signalement,
    get_abonnes_ligne,
    save_abonnement,
)

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
TENANT_ID = os.getenv("TENANT_ID")
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sëtu")


# ─── WEBHOOK VERIFICATION ─────────────────────────────────────

@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return {"error": "Token invalide"}


# ─── WEBHOOK PRINCIPAL ────────────────────────────────────────

@app.post("/webhook")
async def receive(request: Request):
    data = await request.json()

    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" not in entry:
            return {"status": "ok"}

        message = entry["messages"][0]
        sender = message["from"]
        msg_type = message.get("type", "text")
        print(f"\n📩 Message de {sender} | type: {msg_type}")

        text = None
        media_type = "text"

        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
        elif msg_type == "audio":
            media_id = message["audio"]["id"]
            audio_bytes = await download_media(media_id)
            text = await transcribe_audio(audio_bytes)
            media_type = "audio"
            if not text:
                await send_message(sender, "Baal ma, dugguma ko dégg. Jëkkal.")
                return {"status": "ok"}
        else:
            await send_message(sender, "Sëtu dafa xam text ak vocal rekk ci kañ. 🚌")
            return {"status": "ok"}

        if not text or not text.strip():
            return {"status": "ok"}

        print(f"💬 Texte: {text}")

        # ── Contexte utilisateur ──
        contact = await get_or_create_contact(sender, TENANT_ID)
        contact_id = contact["id"]
        conversation = await get_or_create_conversation(contact_id, TENANT_ID)
        conversation_id = conversation["id"]
        history = await get_recent_messages(conversation_id)

        # ── Détection langue ──
        language = await detect_language(text)
        print(f"🌍 Langue: {language}")
        await update_contact_language(contact_id, language)

        # ── Classification intention ──
        intent_result = await classify_intent(text, language)
        intent = intent_result.get("intent", "question")
        confidence = intent_result.get("confidence", 0.5)
        print(f"🎯 Intention: {intent} ({confidence})")

        # ── Sauvegarde message utilisateur ──
        await save_message(
            conversation_id=conversation_id,
            tenant_id=TENANT_ID,
            role="user",
            content=text,
            language=language,
            intent=intent,
            confidence=confidence,
            media_type=media_type
        )

        # ══════════════════════════════════════════
        # PIPELINE SELON L'INTENTION
        # ══════════════════════════════════════════

        reply = None

        # ── CAS 1 : SIGNALEMENT ──────────────────
        if intent == "signalement":
            reply = await handle_signalement(
                text=text,
                sender=sender,
                contact_id=contact_id,
                language=language
            )

        # ── CAS 2 : ABONNEMENT ───────────────────
        elif intent == "abonnement":
            reply = await handle_abonnement(
                text=text,
                sender=sender,
                contact_id=contact_id,
                language=language
            )

        # ── CAS 3 : ESCALADE ─────────────────────
        elif should_escalate(intent, confidence):
            await escalate_conversation(conversation_id, TENANT_ID, intent)
            result = await generate_response(
                message=text,
                history=history,
                language=language,
                intent=intent,
                rag_context="",
                business_name=BUSINESS_NAME,
                is_escalated=True
            )
            reply = result["reply"]

        # ── CAS 4 : QUESTION / AUTRE ─────────────
        else:
            rag_context = ""
            extracted = await extract_signalement(text)
            if extracted.get("ligne"):
                signalements = await search_signalements_recents(
                    extracted["ligne"], TENANT_ID
                )
                rag_context = format_signalements(signalements, extracted["ligne"])

            if not rag_context:
                chunks = await hybrid_search(text, TENANT_ID)
                rag_context = format_context(chunks)

            result = await generate_response(
                message=text,
                history=history,
                language=language,
                intent=intent,
                rag_context=rag_context,
                business_name=BUSINESS_NAME,
                is_escalated=False
            )
            reply = result["reply"]
            response_confidence = result["confidence"]

            if response_confidence < 0.4:
                await escalate_conversation(conversation_id, TENANT_ID, "confiance_faible")
                result = await generate_response(
                    message=text,
                    history=history,
                    language=language,
                    intent=intent,
                    rag_context="",
                    business_name=BUSINESS_NAME,
                    is_escalated=True
                )
                reply = result["reply"]

        if reply:
            await send_message(sender, reply)
            await save_message(
                conversation_id=conversation_id,
                tenant_id=TENANT_ID,
                role="assistant",
                content=reply,
                language=language,
                intent=intent,
                confidence=confidence
            )
            print(f"✅ Réponse envoyée à {sender}")

        return {"status": "ok"}

    except Exception as e:
        print(f"❌ Erreur pipeline: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error"}


# ─── HANDLERS MÉTIER ──────────────────────────────────────────

async def handle_signalement(text: str, sender: str, contact_id: str, language: str) -> str:
    extracted = await extract_signalement(text)
    ligne = extracted.get("ligne")
    position = extracted.get("position")

    if not ligne or not position:
        messages = {
            "fr": "Je n'ai pas bien compris. Écris par exemple : *Bus 15 à Liberté 5* 🚌",
            "wo": "Dugguma ko yëgël. Bind ci kañ : *Bus 15 ci Liberté 5* 🚌",
            "en": "I didn't understand. Write for example: *Bus 15 at Liberté 5* 🚌"
        }
        return messages.get(language, messages["fr"])

    await save_signalement(
        tenant_id=TENANT_ID,
        contact_id=contact_id,
        ligne=ligne,
        position=position
    )
    print(f"📍 Signalement: Bus {ligne} à {position}")

    abonnes = await get_abonnes_ligne(ligne, TENANT_ID)
    alertes_envoyees = 0
    for abonne in abonnes:
        phone = abonne.get("contacts", {}).get("phone")
        if phone and phone != sender:
            alerte = (
                f"🔔 Bus {ligne} signalé à *{position}* il y a quelques instants.\n"
                f"Communauté Sëtu 🚌"
            )
            await send_message(phone, alerte)
            alertes_envoyees += 1

    confirmations = {
        "fr": f"✅ Merci ! Bus {ligne} à *{position}* enregistré.\nTu viens d'aider {alertes_envoyees} personne(s) 🙏",
        "wo": f"✅ Jërejëf ! Bus {ligne} ci *{position}* dundal na.\nDanga ndimbal nit {alertes_envoyees} yi 🙏",
        "en": f"✅ Thanks! Bus {ligne} at *{position}* recorded.\nYou just helped {alertes_envoyees} person(s) 🙏"
    }
    return confirmations.get(language, confirmations["fr"])


async def handle_abonnement(text: str, sender: str, contact_id: str, language: str) -> str:
    extracted = await extract_abonnement(text)
    ligne = extracted.get("ligne")
    arret = extracted.get("arret", "")
    heure = extracted.get("heure", "")

    if not ligne:
        messages = {
            "fr": "Quelle ligne veux-tu suivre ? Écris : *Préviens-moi pour le Bus 15* 🔔",
            "wo": "Ligne bou fenn bëgg nga suivre ? Bind : *Yëgël ma ci Bus 15* 🔔",
            "en": "Which line do you want to follow? Write: *Alert me for Bus 15* 🔔"
        }
        return messages.get(language, messages["fr"])

    await save_abonnement(
        tenant_id=TENANT_ID,
        contact_id=contact_id,
        ligne=ligne,
        arret=arret,
        heure_alerte=heure
    )
    print(f"🔔 Abonnement: {sender} → Bus {ligne} @ {arret}")

    confirmations = {
        "fr": (
            f"🔔 C'est noté ! Je t'alerterai dès que le Bus {ligne} est signalé"
            f"{' près de ' + arret if arret else ''}.\n\n"
            f"Quand tu vois le bus, envoie : *Bus {ligne} à [où tu es]* 🚌"
        ),
        "wo": (
            f"🔔 Dundal na ! Dinaa la yëgël bu Bus {ligne} di signaler"
            f"{' ci ' + arret if arret else ''}.\n\n"
            f"Bu gis nga bus bi, bind : *Bus {ligne} ci [fii nga nekk]* 🚌"
        ),
        "en": (
            f"🔔 Noted! I'll alert you when Bus {ligne} is reported"
            f"{' near ' + arret if arret else ''}.\n\n"
            f"When you see the bus, send: *Bus {ligne} at [your location]* 🚌"
        )
    }
    return confirmations.get(language, confirmations["fr"])


# ─── HEALTH CHECK ─────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "status": "Sëtu OK 🚌",
        "business": BUSINESS_NAME,
        "version": "1.0 MVP",
        "description": "Agent transport Dakar — WhatsApp"
    }
