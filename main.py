from fastapi import FastAPI, Request
from groq import Groq
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# from openai import OpenAI #
# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) #

# ============================================
# CONFIGURATION — tu changeras ça par client
# ============================================

BUSINESS_NAME = "Ma Boutique Dakar"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

SYSTEM_PROMPT = f"""
Tu es un assistant service client pour {BUSINESS_NAME} à Dakar.
- Réponds en Wolof si le client écrit en Wolof
- Réponds en Français si le client écrit en Français
- Sois chaleureux et professionnel
- Si tu ne sais pas, dis-le honnêtement
"""

conversations = {}

# ============================================
# WEBHOOK — vérification Meta
# ============================================

@app.get("/webhook")
async def verify(request: Request):
    params = dict(request.query_params)
    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))
    return {"error": "Token invalide"}

# ============================================
# RECEPTION DES MESSAGES
# ============================================

@app.post("/webhook")
async def receive(request: Request):
    data = await request.json()
    try:
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]
        sender = message["from"]
        text = message.get("text", {}).get("body", "")

        if not text:
            return {"status": "ok"}

        reply = await generate_reply(sender, text)
        await send_message(sender, reply)
        return {"status": "ok"}

    except Exception as e:
        print(f"Erreur: {e}")
        return {"status": "error"}

# ============================================
# GÉNÉRATION RÉPONSE IA
# ============================================

async def generate_reply(sender: str, message: str) -> str:
    if sender not in conversations:
        conversations[sender] = []

    conversations[sender].append({
        "role": "user",
        "content": message
    })

    recent = conversations[sender][-10:]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *recent
        ],
        max_tokens=300
    )

    reply = response.choices[0].message.content

    conversations[sender].append({
        "role": "assistant",
        "content": reply
    })

    return reply

# ============================================
# ENVOI DU MESSAGE WHATSAPP
# ============================================

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
    async with httpx.AsyncClient() as http:
        await http.post(url, json=payload, headers=headers)

# ============================================
# TEST
# ============================================

@app.get("/")
def root():
    return {"status": "Agent actif ✅", "business": BUSINESS_NAME}