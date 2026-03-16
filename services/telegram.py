"""
services/telegram.py — V1.0
Adaptateur Telegram pour Xëtu — Session 3.

RÔLE :
  Reçoit les updates Telegram (webhook POST /telegram/webhook),
  normalise en Contrat Message Universel, appelle le Core Xëtu,
  renvoie la réponse à l'usager via l'API Telegram Bot.

CONTRAT MESSAGE UNIVERSEL respecté :
  Entrée  → {canal, user_id, message, media, ts}
  Sortie  → {user_id, canal, reponse, ts}

ARCHITECTURE :
  Le Core (router → llm → skills) ne sait PAS que le message vient
  de Telegram. Il reçoit un phone/user_id et un texte. C'est tout.

VARIABLES D'ENV REQUISES :
  TELEGRAM_BOT_TOKEN  → token BotFather (ex: 110201543:AAHdq...)

NOTES :
  - user_id Telegram = entier, on le préfixe "tg_" pour éviter les
    collisions avec les numéros WhatsApp dans Supabase.
  - Pas de validation HMAC ici (Telegram utilise un secret optionnel
    sur le webhook — on peut l'ajouter plus tard via set_webhook secret_token).
  - Les messages vocaux Telegram sont ignorés pour l'instant (TODO: Whisper).
  - Les photos/documents sont ignorés (même comportement que WhatsApp).
"""

import logging
import httpx
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

def _get_token() -> str:
    import os
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("❌ TELEGRAM_BOT_TOKEN manquant dans .env")
    return token


def _api_url(method: str) -> str:
    return f"https://api.telegram.org/bot{_get_token()}/{method}"


# ═══════════════════════════════════════════════════════════
# ENVOI DE MESSAGE
# ═══════════════════════════════════════════════════════════

async def send_message(chat_id: int | str, text: str) -> bool:
    """
    Envoie un message texte à un chat Telegram.
    Utilise parse_mode=Markdown pour compatibilité avec les *bold*
    déjà utilisés dans les réponses du Core Xëtu.
    Retourne True si succès, False sinon.
    """
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(_api_url("sendMessage"), json=payload)
            if res.status_code != 200:
                logger.error(f"[Telegram] sendMessage error {res.status_code}: {res.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[Telegram] send_message exception: {e}")
        return False


# ═══════════════════════════════════════════════════════════
# PARSING DU WEBHOOK
# ═══════════════════════════════════════════════════════════

def parse_incoming_update(payload: dict) -> dict | None:
    """
    Parse un update Telegram reçu sur le webhook.

    Retourne un dict normalisé :
      {
        "user_id"   : "tg_123456789",   ← préfixé pour Supabase
        "chat_id"   : 123456789,        ← pour répondre
        "text"      : "Bus 15 à Liberté 5",
        "ts"        : "2026-03-10T08:32:00Z",
        "canal"     : "telegram",
      }

    Retourne None si :
      - Pas de message texte (photo, sticker, voice, etc.)
      - Message d'un bot
      - Update sans message (callback_query, etc.)
    """
    try:
        message = payload.get("message")
        if not message:
            # On ignore : callback_query, edited_message, channel_post...
            logger.debug("[Telegram] Update sans message texte — ignoré")
            return None

        # Ignorer les messages de bots
        sender = message.get("from", {})
        if sender.get("is_bot"):
            return None

        # Récupérer le texte
        text = message.get("text", "").strip()
        if not text:
            # Voice, photo, sticker, document → ignoré (même comportement que WhatsApp)
            msg_type = _detect_message_type(message)
            logger.info(f"[Telegram] Message non-texte ({msg_type}) — ignoré")
            return None

        chat_id    = message["chat"]["id"]
        tg_user_id = sender.get("id", chat_id)

        # Timestamp de l'update Telegram (epoch) ou now()
        ts_epoch = message.get("date")
        if ts_epoch:
            ts = datetime.fromtimestamp(ts_epoch, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        else:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "user_id" : f"tg_{tg_user_id}",   # Contrat Message Universel
            "chat_id" : chat_id,               # Pour send_message()
            "text"    : text,
            "ts"      : ts,
            "canal"   : "telegram",
        }

    except (KeyError, TypeError) as e:
        logger.warning(f"[Telegram] Erreur parsing update: {e}")
        return None


def _detect_message_type(message: dict) -> str:
    """Détecte le type de message non-texte pour le log."""
    for t in ("voice", "audio", "photo", "video", "document", "sticker", "location"):
        if t in message:
            return t
    return "unknown"


# ═══════════════════════════════════════════════════════════
# ENREGISTREMENT DU WEBHOOK
# ═══════════════════════════════════════════════════════════

async def set_webhook(public_url: str, secret_token: str | None = None) -> bool:
    """
    Enregistre l'URL du webhook auprès de Telegram.
    À appeler une seule fois après chaque changement d'URL ou de secret.

    Args:
        public_url  : URL publique HTTPS de ton service
        secret_token: secret choisi librement (32-256 chars alphanum).
                      Telegram l'enverra dans X-Telegram-Bot-Api-Secret-Token.
                      Doit correspondre à TELEGRAM_WEBHOOK_SECRET dans Railway.
    """
    import os
    webhook_url = f"{public_url.rstrip('/')}/telegram/webhook"
    # Lire depuis l'env si non passé en argument
    if not secret_token:
        secret_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    payload: dict = {"url": webhook_url}
    if secret_token:
        payload["secret_token"] = secret_token
        logger.info(f"[Telegram] setWebhook avec secret_token ✅")
    else:
        logger.warning("[Telegram] setWebhook sans secret_token — endpoint non sécurisé")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                _api_url("setWebhook"),
                json=payload
            )
            data = res.json()
            if data.get("ok"):
                logger.info(f"✅ Telegram webhook enregistré → {webhook_url}")
                return True
            else:
                logger.error(f"[Telegram] setWebhook failed: {data}")
                return False
    except Exception as e:
        logger.error(f"[Telegram] set_webhook exception: {e}")
        return False


async def get_webhook_info() -> dict:
    """
    Retourne les infos du webhook actuel (pour debug).
    Utile pour vérifier que le webhook est bien enregistré.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(_api_url("getWebhookInfo"))
            return res.json()
    except Exception as e:
        logger.error(f"[Telegram] get_webhook_info exception: {e}")
        return {}