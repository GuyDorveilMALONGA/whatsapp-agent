from fastapi import FastAPI, Request
from groq import Groq
import httpx
import os
import tempfile
import edge_tts
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

BUSINESS_NAME = "Ma Boutique Dakar"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

SYSTEM_PROMPT = f"""
Tu t'appelles Ami, assistante de {BUSINESS_NAME} à Dakar.

Tu es chaleureuse, directe et humaine — comme une vraie Dakaroise sympa qui connaît bien sa boutique.

Tu réponds TOUJOURS en Français, quelle que soit la langue du client.

STYLE D'ÉCRITURE :
- Réponds toujours en phrases courtes et directes
- Maximum 2-3 phrases par paragraphe
- Laisse une ligne vide entre chaque idée
- Jamais de longues listes ennuyeuses
- Utilise des mots simples, chaleureux, du quotidien

STYLE VOCAL :
- Parle comme si tu souriais
- Utilise des petites expressions naturelles : "Bien sûr !", "Absolument !", "Avec plaisir !"
- Rythme naturel — ni trop vite, ni trop lent

COMPORTEMENT :
- Va droit au but, ne tourne pas autour du pot
- Si tu ne sais pas → dis-le honnêtement et propose d'aider autrement
- Si le client est en colère → reste calme, empathique, solution d'abord
- Ne répète jamais la question du client avant de répondre
- Ne dis jamais "Je suis une IA" sauf si on te le demande directement

IMPORTANT :
- Tu représentes {BUSINESS_NAME} avec fierté
- Chaque client doit se sentir accueilli comme à la boutique
"""

conversations = {}

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
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        sender = message["from"]
        msg_type = message.get("type")

        # MESSAGE TEXTE → réponse TEXTE
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
            if not text:
                return {"status": "ok"}
            reply = await generate_reply(sender, text)
            await send_text_message(sender, reply)

        # MESSAGE VOCAL → réponse VOCALE
        elif msg_type in ["audio", "voice"]:
            audio_id = message.get("audio", {}).get("id") or message.get("voice", {}).get("id")
            if not audio_id:
                return {"status": "ok"}
            text = await transcribe_audio(audio_id)
            print(f"Transcription: {text}")
            reply = await generate_reply(sender, text)
            await send_voice_message(sender, reply)

        return {"status": "ok"}

    except Exception as e:
        print(f"Erreur: {e}")
        return {"status": "error"}

async def transcribe_audio(audio_id: str) -> str:
    url = f"https://graph.facebook.com/v18.0/{audio_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient(timeout=30) as http:
        res = await http.get(url, headers=headers)
        audio_url = res.json().get("url")
        audio_res = await http.get(audio_url, headers=headers)
        audio_data = audio_res.content
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(audio_data)
        tmp_path = f.name
    with open(tmp_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=("audio.ogg", f, "audio/ogg"),
            model="whisper-large-v3",
        )
    os.unlink(tmp_path)
    return transcription.text

async def generate_reply(sender: str, message: str) -> str:
    if sender not in conversations:
        conversations[sender] = []
    conversations[sender].append({"role": "user", "content": message})
    recent = conversations[sender][-10:]
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, *recent],
        max_tokens=300
    )
    reply = response.choices[0].message.content
    conversations[sender].append({"role": "assistant", "content": reply})
    return reply

async def send_text_message(to: str, message: str):
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    async with httpx.AsyncClient(timeout=30) as http:
        res = await http.post(url, json=payload, headers=headers)
        print(f"Texte réponse: {res.status_code}")

async def send_voice_message(to: str, message: str):
    # 1. Générer audio avec Edge TTS (Microsoft, gratuit)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    communicate = edge_tts.Communicate(message, voice="fr-FR-DeniseNeural")
    await communicate.save(tmp_path)
    print("Audio généré avec Edge TTS ✅")

    # 2. Uploader + envoyer sur WhatsApp
    async with httpx.AsyncClient(timeout=30) as http:
        meta_headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
        with open(tmp_path, "rb") as f:
            upload_res = await http.post(
                f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/media",
                headers=meta_headers,
                data={"messaging_product": "whatsapp"},
                files={"file": ("voice.mp3", f, "audio/mpeg")}
            )
        media_id = upload_res.json().get("id")
        print(f"Media ID: {media_id}")
        res = await http.post(
            f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages",
            headers={**meta_headers, "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": to, "type": "audio", "audio": {"id": media_id}}
        )
        print(f"Vocal réponse: {res.status_code}")

    os.unlink(tmp_path)

@app.get("/")
def root():
    return {"status": "Agent actif ✅", "business": BUSINESS_NAME}