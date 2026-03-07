from fastapi import FastAPI, Request
from dotenv import load_dotenv
import os

load_dotenv()

from services.whatsapp import send_message, download_media
from services.whisper import transcribe_audio
from services.language import detect_language
from agents.router import classify_intent, should_escalate
from agents.responder import generate_response
from rag.retriever import hybrid_search, format_context
from db.context import (
    get_or_create_contact,
    get_or_create_conversation,
    get_recent_messages,
    save_message,
    update_contact_language,
    escalate_conversation
)

app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
TENANT_ID = os.getenv("TENANT_ID")
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "afri ai")


@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return {"error": "Token invalide"}


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
        print(f"Message de {sender} type: {msg_type}")

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
                await send_message(sender, "Desole, je n'ai pas pu comprendre votre message vocal.")
                return {"status": "ok"}
        else:
            await send_message(sender, "Je peux traiter les messages texte et vocaux pour le moment.")
            return {"status": "ok"}

        if not text or not text.strip():
            return {"status": "ok"}

        contact = await get_or_create_contact(sender, TENANT_ID)
        contact_id = contact["id"]

        conversation = await get_or_create_conversation(contact_id, TENANT_ID)
        conversation_id = conversation["id"]

        history = await get_recent_messages(conversation_id)

        language = await detect_language(text)
        print(f"Langue: {language}")

        await update_contact_language(contact_id, language)

        intent_result = await classify_intent(text, language)
        intent = intent_result.get("intent", "question")
        confidence = intent_result.get("confidence", 0.5)
        print(f"Intention: {intent} ({confidence})")

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

        if should_escalate(intent, confidence):
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
            await send_message(sender, result["reply"])
            await save_message(
                conversation_id=conversation_id,
                tenant_id=TENANT_ID,
                role="assistant",
                content=result["reply"],
                language=language,
                intent="escalate",
                confidence=1.0
            )
            return {"status": "ok"}

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

        await save_message(
            conversation_id=conversation_id,
            tenant_id=TENANT_ID,
            role="assistant",
            content=reply,
            language=language,
            intent=intent,
            confidence=response_confidence
        )

        await send_message(sender, reply)
        print(f"Reponse envoyee a {sender}")
        return {"status": "ok"}

    except Exception as e:
        print(f"Erreur pipeline: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error"}


@app.get("/")
def root():
    return {
        "status": "afri ai agent OK",
        "business": BUSINESS_NAME,
        "version": "2.0 MVP"
    }
