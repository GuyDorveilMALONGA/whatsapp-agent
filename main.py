from fastapi import FastAPI, Request
from groq import Groq
import httpx
import os
import tempfile
from gtts import gTTS
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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
        value = data["entry"][0]["changes"][0]["value"]

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        sender = message["from"]
        msg_type = message.get("type")

        # MESSAGE TEXTE
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
            if not text:
                return {"status": "ok"}
            reply = await generate_reply(sender, text)
            await send_text_message(sender, reply)

        # MESSAGE VOCAL
        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            text = await transcribe_audio(audio_id)
            if not text:
                return {"status": "ok"}
            print(f"Transcription: {text}")
            reply = await generate_reply(sender, text)
            await send_voice_message(sender, reply)

        return {"status": "ok"}

    except Exception as e:
        print(f"Erreur: {e}")
        return {"status": "error"}

# ============================================
# TRANSCRIPTION AUDIO → TEXTE (Whisper/Groq)
# ============================================

async def transcribe_audio(audio_id: str) -> str:
    # 1. Télécharger l'audio depuis Meta
    url = f"https://graph.facebook.com/v18.0/{audio_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient() as http:
        # Récupérer l'URL du fichier
        res = await http.get(url, headers=headers)
        audio_url = res.json().get("url")

        # Télécharger le fichier audio
        audio_res = await http.get(audio_url, headers=headers)
        audio_data = audio_res.content

    # 2. Transcrire avec Whisper (Groq)
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
# ENVOI MESSAGE TEXTE
# ============================================

async def send_text_message(to: str, message: str):
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
        response = await http.post(url, json=payload, headers=headers)
        print(f"Meta réponse: {response.status_code} - {response.text}")

# ============================================
# ENVOI NOTE VOCALE
# ============================================

async def send_voice_message(to: str, message: str):
    # 1. Convertir texte → audio avec gTTS
    tts = gTTS(text=message, lang="fr")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tts.save(f.name)
        tmp_path = f.name

    # 2. Uploader l'audio sur Meta
    upload_url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient() as http:
        with open(tmp_path, "rb") as f:
            upload_res = await http.post(
                upload_url,
                headers=headers,
                data={"messaging_product": "whatsapp"},
                files={"file": ("voice.mp3", f, "audio/mpeg")}
            )
        media_id = upload_res.json().get("id")
        print(f"Media ID: {media_id}")

        # 3. Envoyer la note vocale
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id}
        }
        response = await http.post(
            f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages",
            headers={**headers, "Content-Type": "application/json"},
            json=payload
        )
        print(f"Vocal réponse: {response.status_code} - {response.text}")

    os.unlink(tmp_path)



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

        # MESSAGE TEXTE
        if msg_type == "text":
            text = message.get("text", {}).get("body", "")
            if not text:
                return {"status": "ok"}
            reply = await generate_reply(sender, text)
            
            # Détecter la langue pour choisir le format de réponse
            lang = detect_language(text)
            if lang == "fr":
                await send_voice_message(sender, reply)  # Vocal en Français
            else:
                await send_text_message(sender, reply)   # Texte en Wolof

        # MESSAGE VOCAL
        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            text = await transcribe_audio(audio_id)
            if not text:
                return {"status": "ok"}
            reply = await generate_reply(sender, text)
            
            lang = detect_language(text)
            if lang == "fr":
                await send_voice_message(sender, reply)  # Vocal en Français
            else:
                await send_text_message(sender, reply)   # Texte en Wolof

        return {"status": "ok"}

    except Exception as e:
        print(f"Erreur: {e}")
        return {"status": "error"}
    

def detect_language(text: str) -> str:
    # Mots courants en Wolof
    wolof_words = ["waaw", "deedeet", "nanga", "def", "lan", "moo", "xam", 
                   "nit", "jaay", "jënd", "bës", "suba", "guddi", "yow", "maa"]
    
    text_lower = text.lower()
    for word in wolof_words:
        if word in text_lower:
            return "wo"  # Wolof
    return "fr"  # Français par défaut

# ============================================
# TEST
# ============================================

@app.get("/")
def root():
    return {"status": "Agent actif ✅", "business": BUSINESS_NAME}
