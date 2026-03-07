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
VOICE_ID = os.getenv("VOICE_ID")

SYSTEM_PROMPT = """
Tu es Ami, assistante de Ma Boutique Dakar.
Tu es chaleureuse et professionnelle.
Réponds toujours en français.
"""

conversations = {}

@app.get("/")
def root():
    return {"status": "Agent actif", "business": BUSINESS_NAME}


@app.get("/webhook")
async def verify(request: Request):

    params = dict(request.query_params)

    if params.get("hub.verify_token") == VERIFY_TOKEN:
        return int(params.get("hub.challenge"))

    return {"error": "token invalide"}


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

            text = message["text"]["body"]

            reply = await generate_reply(sender, text)

            await send_voice_message(sender, reply)

        elif msg_type == "audio":

            audio_id = message["audio"]["id"]

            text = await transcribe_audio(audio_id)

            reply = await generate_reply(sender, text)

            await send_voice_message(sender, reply)

        return {"status": "ok"}

    except Exception as e:

        print("Erreur:", e)

        return {"status": "error"}


async def transcribe_audio(audio_id: str):

    url = f"https://graph.facebook.com/v18.0/{audio_id}"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
    }

    async with httpx.AsyncClient() as http:

        res = await http.get(url, headers=headers)

        audio_url = res.json()["url"]

        audio = await http.get(audio_url, headers=headers)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as f:

        f.write(audio.content)

        path = f.name

    with open(path, "rb") as f:

        transcription = client.audio.transcriptions.create(
            file=("audio.ogg", f),
            model="whisper-large-v3"
        )

    os.unlink(path)

    return transcription.text


async def generate_reply(sender, text):

    if sender not in conversations:
        conversations[sender] = []

    conversations[sender].append({
        "role": "user",
        "content": text
    })

    conversations[sender] = conversations[sender][-10:]

    response = client.chat.completions.create(

        model="llama-3.1-8b-instant",

        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            *conversations[sender]
        ]

    )

    reply = response.choices[0].message.content

    conversations[sender].append({
        "role": "assistant",
        "content": reply
    })

    return reply


async def send_text_message(to, message):

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


async def send_voice_message(to, message):

    try:

        async with httpx.AsyncClient(timeout=30) as http:

            tts = await http.post(

                f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",

                headers={
                    "xi-api-key": ELEVENLABS_API_KEY,
                    "Content-Type": "application/json"
                },

                json={
                    "text": message,
                    "model_id": "eleven_multilingual_v2"
                }

            )

        if tts.status_code != 200:

            print("Erreur ElevenLabs:", tts.text)

            await send_text_message(to, message)

            return

        audio_data = tts.content

        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:

            f.write(audio_data)

            path = f.name

        async with httpx.AsyncClient() as http:

            with open(path, "rb") as f:

                upload = await http.post(

                    f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/media",

                    headers={
                        "Authorization": f"Bearer {WHATSAPP_TOKEN}"
                    },

                    data={"messaging_product": "whatsapp"},

                    files={
                        "file": ("voice.mp3", f, "audio/mpeg")
                    }

                )

            media_id = upload.json()["id"]

            await http.post(

                f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages",

                headers={
                    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                    "Content-Type": "application/json"
                },

                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "audio",
                    "audio": {"id": media_id}
                }

            )

        os.unlink(path)

    except Exception as e:

        print("Erreur voice:", e)

        await send_text_message(to, message)