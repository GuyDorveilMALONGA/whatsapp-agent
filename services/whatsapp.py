import httpx
import os

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")


async def send_message(to: str, message: str):
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"WhatsApp API: {response.status_code}")
        return response


async def download_media(media_id: str) -> bytes:
    """Télécharge un fichier audio depuis WhatsApp"""
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"https://graph.facebook.com/v18.0/{media_id}",
            headers=headers
        )
        media_url = r.json().get("url")
        r2 = await client.get(media_url, headers=headers)
        return r2.content
