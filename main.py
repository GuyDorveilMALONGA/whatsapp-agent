from fastapi import FastAPI, Request
from groq import Groq
import httpx
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

BUSINESS_NAME = "Ma Boutique Dakar"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = "O31r762Gb3WFygrEOGh0"

SYSTEM_PROMPT = "Tu es Ami, assistante de Ma Boutique Dakar. Réponds toujours en français, sois chaleureuse et directe."

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

        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
            if not text:
                return {"status": "ok"}
            reply = await generate_reply(sender, text)
            await send_text_message(sender, reply)

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
    print(f"ElevenLabs KEY: {ELEVENLABS_API_KEY[:10] if ELEVENLABS_API_KEY else 'VIDE!'}")

    # 1. Générer audio ElevenLabs
    async with httpx.AsyncClient(timeout=30) as http:
        tts_res = await http.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": message,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
            }
        )
        print(f"ElevenLabs status: {tts_res.status_code}")
        audio_data = tts_res.content

    # 2. Sauvegarder
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio_data)
        tmp_path = f.name

    # 3. Uploader + envoyer sur WhatsApp
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