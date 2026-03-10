"""
core/security.py — V7.0 (NOUVEAU)
Trois responsabilités :
  1. Vérification HMAC des webhooks Meta
  2. Validation du numéro de téléphone
  3. Rate limiting par phone + global

Tous les modules de sécurité sont ici — zéro logique dans main.py.
"""
import hashlib
import hmac
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
    Vérifie que le phone est au format E.164 : +XXXXXXXXXXXX
    Entre 7 et 15 chiffres après le +.
    """
    if not phone:
        return False
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
