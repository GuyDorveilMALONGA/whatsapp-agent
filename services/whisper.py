"""
services/whisper.py — V2
Transcription audio → texte via Groq Whisper.
S'insère dans main.py avant la détection de langue.
"""
import httpx
import logging
from groq import AsyncGroq
from config.settings import GROQ_API_KEY, WHATSAPP_TOKEN

logger = logging.getLogger(__name__)

_groq = AsyncGroq(api_key=GROQ_API_KEY)


async def transcribe(audio_id: str) -> str | None:
    """
    1. Télécharge le fichier audio depuis WhatsApp (via l'ID média)
    2. L'envoie à Groq Whisper
    3. Retourne le texte transcrit, ou None si échec
    """
    audio_bytes = await _download_whatsapp_audio(audio_id)
    if not audio_bytes:
        return None

    try:
        transcription = await _groq.audio.transcriptions.create(
            file=("audio.ogg", audio_bytes, "audio/ogg"),
            model="whisper-large-v3",
            language=None,          # Auto-détection de la langue
            response_format="text",
        )
        text = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        logger.info(f"[Whisper] Transcription OK : {text[:60]}...")
        return text

    except Exception as e:
        logger.error(f"[Whisper] Erreur transcription: {e}")
        return None


async def _download_whatsapp_audio(media_id: str) -> bytes | None:
    """
    Récupère les bytes audio depuis l'API Meta.
    Étape 1 : récupère l'URL du fichier
    Étape 2 : télécharge le fichier
    """
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Étape 1 : récupère l'URL
            res = await client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers=headers
            )
            if res.status_code != 200:
                logger.error(f"[Whisper] Erreur récupération URL media: {res.status_code}")
                return None

            url = res.json().get("url")
            if not url:
                return None

            # Étape 2 : télécharge le fichier audio
            audio_res = await client.get(url, headers=headers)
            if audio_res.status_code != 200:
                logger.error(f"[Whisper] Erreur téléchargement audio: {audio_res.status_code}")
                return None

            return audio_res.content

    except Exception as e:
        logger.error(f"[Whisper] Erreur download: {e}")
        return None
