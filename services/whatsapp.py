"""
services/whatsapp.py
Point unique d'envoi de messages WhatsApp.
"""
import httpx
import logging
from config.settings import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

logger = logging.getLogger(__name__)

WA_API_URL = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_ID}/messages"

HEADERS = {
    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
    "Content-Type": "application/json",
}


async def send_message(phone: str, text: str) -> bool:
    """
    Envoie un message texte WhatsApp.
    Retourne True si succès, False sinon.
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "text",
        "text": {"body": text}
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(WA_API_URL, headers=HEADERS, json=payload)
            if res.status_code != 200:
                logger.error(f"WhatsApp error {res.status_code}: {res.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"WhatsApp send_message exception: {e}")
        return False


def parse_incoming_message(payload: dict) -> dict | None:
    """
    Parse le payload webhook Meta.
    Retourne un dict avec : phone, message_type, text, audio_id
    Retourne None si le payload ne contient pas de message utilisateur.
    """
    try:
        entry = payload["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return None

        msg = value["messages"][0]
        phone = msg["from"]
        msg_type = msg["type"]

        text = None
        audio_id = None

        if msg_type == "text":
            text = msg["text"]["body"].strip()
        elif msg_type == "audio":
            audio_id = msg["audio"]["id"]
        elif msg_type in ("image", "document", "video"):
            # On ignore les médias non supportés
            return None

        return {
            "phone": phone,
            "message_type": msg_type,
            "text": text,
            "audio_id": audio_id,
            "message_id": msg.get("id"),
        }
    except (KeyError, IndexError, TypeError):
        return None
