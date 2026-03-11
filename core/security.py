"""
core/security.py — V7.1
Trois responsabilités :
  1. Vérification HMAC des webhooks Meta
  2. Validation du numéro de téléphone
  3. Rate limiting par phone + global

MIGRATIONS V7.1 depuis V7.0 :
  - validate_phone() accepte les session_id web "web_uuid4"
    Sans ce fix, le chat WebSocket du dashboard retournait
    "Une erreur s'est produite" sur chaque message — le session_id
    "web_uuid4..." ne passait pas la regex E.164 → crash silencieux
    dans _process_message_safe. WhatsApp n'était pas affecté car
    la validation se fait avant d'entrer dans le pipeline partagé.
"""
import hashlib
import hmac
import re
import time
import logging
from collections import defaultdict

from config.settings import (
    WHATSAPP_APP_SECRET,
    PHONE_REGEX,
    RATE_LIMIT_PER_PHONE_PER_MIN,
    RATE_LIMIT_GLOBAL_PER_MIN,
)

logger = logging.getLogger(__name__)

# Format session_id web dashboard : "web_<uuid4>"
_WEB_SESSION_RE = re.compile(
    r"^web_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════
# 1. VÉRIFICATION HMAC WEBHOOK META
# ══════════════════════════════════════════════════════════

def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None) -> bool:
    """
    Vérifie le X-Hub-Signature-256 envoyé par Meta.
    Retourne True si valide, False sinon.

    Meta envoie : "sha256=<hex_digest>"
    On recalcule le HMAC-SHA256 du body avec l'app_secret.
    """
    if not signature_header:
        logger.warning("[Security] Webhook sans signature X-Hub-Signature-256")
        return False

    if not signature_header.startswith("sha256="):
        logger.warning("[Security] Format signature invalide")
        return False

    expected_sig = signature_header[7:]  # enlève "sha256="

    computed = hmac.new(
        key=WHATSAPP_APP_SECRET.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, expected_sig):
        logger.warning("[Security] Signature HMAC invalide — requête rejetée")
        return False

    return True


# ══════════════════════════════════════════════════════════
# 2. VALIDATION PHONE
# ══════════════════════════════════════════════════════════

def validate_phone(phone: str | None) -> bool:
    """
    Vérifie que l'identifiant est valide.

    Accepte :
      - Numéros E.164 WhatsApp/Telegram : +XXXXXXXXXXXX (7–15 chiffres)
      - Session ID web dashboard : web_<uuid4>

    FIX V7.1 : les sessions WebSocket ont le format "web_uuid4".
    Sans ce fix, _process_message_safe crashait silencieusement
    pour toutes les requêtes chat web.
    """
    if not phone:
        return False

    # Sessions web dashboard — toujours valides
    if _WEB_SESSION_RE.match(phone):
        return True

    # Numéros téléphone E.164
    return bool(PHONE_REGEX.match(phone))


# ══════════════════════════════════════════════════════════
# 3. RATE LIMITING (en mémoire — migrer vers Redis si multi-instance)
# ══════════════════════════════════════════════════════════

# Stocke les timestamps des messages par phone
_phone_timestamps: dict[str, list[float]] = defaultdict(list)
_global_timestamps: list[float] = []

# Nettoyage automatique toutes les 60s
_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 60.0
_WINDOW = 60.0  # fenêtre de 1 minute


def _cleanup_old_entries():
    """Nettoie les timestamps > 1 minute pour libérer la RAM."""
    global _last_cleanup, _global_timestamps
    now = time.monotonic()

    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return

    cutoff = now - _WINDOW
    _global_timestamps = [t for t in _global_timestamps if t > cutoff]

    to_delete = []
    for phone, timestamps in _phone_timestamps.items():
        fresh = [t for t in timestamps if t > cutoff]
        if fresh:
            _phone_timestamps[phone] = fresh
        else:
            to_delete.append(phone)

    for phone in to_delete:
        del _phone_timestamps[phone]

    _last_cleanup = now


def check_rate_limit(phone: str) -> bool:
    """
    Retourne True si le message est autorisé, False si rate-limité.
    Vérifie deux niveaux :
      1. Par phone : max N messages / minute
      2. Global : max M messages / minute
    """
    now = time.monotonic()
    cutoff = now - _WINDOW

    _cleanup_old_entries()

    # Check global
    recent_global = [t for t in _global_timestamps if t > cutoff]
    if len(recent_global) >= RATE_LIMIT_GLOBAL_PER_MIN:
        logger.warning(f"[RateLimit] Global limit atteint ({RATE_LIMIT_GLOBAL_PER_MIN}/min)")
        return False

    # Check per-phone
    recent_phone = [t for t in _phone_timestamps[phone] if t > cutoff]
    if len(recent_phone) >= RATE_LIMIT_PER_PHONE_PER_MIN:
        logger.warning(f"[RateLimit] Phone {phone[-4:]} limité ({RATE_LIMIT_PER_PHONE_PER_MIN}/min)")
        return False

    # Autorisé — enregistre le timestamp
    _global_timestamps.append(now)
    _phone_timestamps[phone].append(now)
    return True