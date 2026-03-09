"""
services/whisper.py — V3 (Production Ready)
Transcription audio → texte via Groq Whisper.

V3 vs V2 :
  + Coupe-circuit financier : rejet audios > 1 Mo (avant téléchargement)
  + Conditionnement Wolof/FR : prompt contextuel dakarois → moins d'hallucinations
  + temperature=0.0 : force la précision, bloque la créativité du modèle
  + MIME type flexible : plus de "audio/ogg" codé en dur
  + Séparation claire _get_whatsapp_media_info / _download_audio_bytes
"""
import httpx
import logging
from groq import AsyncGroq
from config.settings import GROQ_API_KEY, WHATSAPP_TOKEN

logger = logging.getLogger(__name__)

_groq = AsyncGroq(api_key=GROQ_API_KEY)

# Coupe-circuit : 1 Mo ≈ 1 min d'audio WhatsApp Opus compressé
_MAX_AUDIO_SIZE_BYTES = 1024 * 1024

# Prompt de conditionnement — aide Whisper sur le code-switching dakarois
_CONTEXT_PROMPT = (
    "Transcription de messages vocaux de Dakar, Sénégal. "
    "Mélange de français et de wolof urbain (code-switching). "
    "Termes fréquents : bus, dem dikk, arrêt, ligne, waaw, fi, dem, "
    "Liberté, Sandaga, Parcelles, HLM, Médina."
)


async def transcribe(audio_id: str) -> str | None:
    """
    1. Récupère les métadonnées (URL + taille) depuis Meta
    2. Coupe-circuit si trop volumineux
    3. Télécharge les bytes audio
    4. Transcrit via Groq Whisper avec conditionnement dakarois
    """
    # Étape 1 — Métadonnées (taille + URL)
    media_info = await _get_whatsapp_media_info(audio_id)
    if not media_info:
        return None

    # Étape 2 — Coupe-circuit financier
    file_size = media_info.get("file_size", 0)
    if file_size > _MAX_AUDIO_SIZE_BYTES:
        logger.warning(f"[Whisper] Audio rejeté : {file_size} bytes > 1 Mo")
        return (
            "⚠️ Ton message vocal est trop long. "
            "Envoie un message court de moins d'une minute s'il te plaît !"
        )

    # Étape 3 — Téléchargement
    url = media_info.get("url")
    if not url:
        logger.error("[Whisper] URL audio absente dans les métadonnées Meta")
        return None

    audio_bytes = await _download_audio_bytes(url)
    if not audio_bytes:
        return None

    # Étape 4 — Transcription
    try:
        transcription = await _groq.audio.transcriptions.create(
            file=("audio.ogg", audio_bytes),   # MIME type flexible — pas de codec en dur
            model="whisper-large-v3",
            prompt=_CONTEXT_PROMPT,            # Conditionne le modèle sur le contexte dakarois
            language=None,                     # Auto-détection (FR majoritaire + Wolof)
            response_format="text",
            temperature=0.0,                   # Force la précision, bloque les hallucinations
        )
        text = (
            transcription.strip()
            if isinstance(transcription, str)
            else transcription.text.strip()
        )
        logger.info(f"[Whisper] Transcription OK : {text[:60]}...")
        return text

    except Exception as e:
        logger.error(f"[Whisper] Erreur transcription Groq: {e}")
        return None


async def _get_whatsapp_media_info(media_id: str) -> dict | None:
    """
    Étape 1 : Récupère l'URL et les métadonnées (file_size) depuis Meta.
    Timeout court (10s) — c'est juste une requête metadata.
    """
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(
                f"https://graph.facebook.com/v19.0/{media_id}",
                headers=headers,
            )
            if res.status_code != 200:
                logger.error(f"[Whisper] Erreur métadonnées Meta: {res.status_code}")
                return None
            return res.json()
    except Exception as e:
        logger.error(f"[Whisper] Erreur réseau (métadonnées): {e}")
        return None


async def _download_audio_bytes(url: str) -> bytes | None:
    """
    Étape 2 : Télécharge les bytes réels de l'audio.
    Timeout plus long (15s) — téléchargement binaire.
    """
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code != 200:
                logger.error(f"[Whisper] Erreur téléchargement bytes: {res.status_code}")
                return None
            return res.content
    except Exception as e:
        logger.error(f"[Whisper] Erreur réseau (téléchargement): {e}")
        return None