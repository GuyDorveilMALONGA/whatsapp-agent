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
# 3. RATE LIMITING — Redis si disponible, mémoire locale sinon
# ══════════════════════════════════════════════════════════
# Redis (multi-worker safe) : INCR + EXPIRE sur clés phone/global.
# Fallback local (1 worker) : liste de timestamps en mémoire.

_phone_timestamps: dict[str, list[float]] = defaultdict(list)
_global_timestamps: list[float] = []
_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 60.0
_WINDOW = 60.0

_rl_redis       = None
_rl_redis_failed = False


def _get_rl_redis():
    global _rl_redis, _rl_redis_failed
    if _rl_redis_failed:
        return None
    if _rl_redis is not None:
        return _rl_redis
    try:
        import os
        import redis
        url = os.environ.get("REDIS_URL") or os.environ.get("REDISCLOUD_URL")
        if not url:
            _rl_redis_failed = True
            return None
        _rl_redis = redis.from_url(url, decode_responses=True)
        _rl_redis.ping()
        return _rl_redis
    except Exception:
        _rl_redis_failed = True
        return None


def _check_rate_limit_redis(r, phone: str) -> bool:
    """Rate limit via Redis INCR/EXPIRE — multi-worker safe."""
    import time as _time
    window = int(_WINDOW)
    try:
        pipe = r.pipeline()
        key_phone  = f"xetu:rl:phone:{phone}"
        key_global = "xetu:rl:global"
        pipe.incr(key_phone)
        pipe.expire(key_phone, window)
        pipe.incr(key_global)
        pipe.expire(key_global, window)
        results = pipe.execute()
        count_phone, _, count_global, _ = results
        if count_global > RATE_LIMIT_GLOBAL_PER_MIN:
            logger.warning(f"[RateLimit] Global Redis ({count_global}/{RATE_LIMIT_GLOBAL_PER_MIN}/min)")
            return False
        if count_phone > RATE_LIMIT_PER_PHONE_PER_MIN:
            logger.warning(f"[RateLimit] Phone {phone[-4:]} Redis ({count_phone}/{RATE_LIMIT_PER_PHONE_PER_MIN}/min)")
            return False
        return True
    except Exception as e:
        logger.warning(f"[RateLimit] Redis erreur, fallback local: {e}")
        return None  # None = fallback


def _cleanup_old_entries():
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
    Retourne True si autorisé, False si rate-limité.
    Redis si disponible (multi-worker), mémoire locale sinon.
    """
    # Essayer Redis d'abord
    r = _get_rl_redis()
    if r:
        result = _check_rate_limit_redis(r, phone)
        if result is not None:
            return result
        # Redis a échoué → fallback local ci-dessous

    # Fallback mémoire locale
    now = time.monotonic()
    cutoff = now - _WINDOW
    _cleanup_old_entries()

    recent_global = [t for t in _global_timestamps if t > cutoff]
    if len(recent_global) >= RATE_LIMIT_GLOBAL_PER_MIN:
        logger.warning(f"[RateLimit] Global local ({RATE_LIMIT_GLOBAL_PER_MIN}/min)")
        return False

    recent_phone = [t for t in _phone_timestamps[phone] if t > cutoff]
    if len(recent_phone) >= RATE_LIMIT_PER_PHONE_PER_MIN:
        logger.warning(f"[RateLimit] Phone {phone[-4:]} local ({RATE_LIMIT_PER_PHONE_PER_MIN}/min)")
        return False

    _global_timestamps.append(now)
    _phone_timestamps[phone].append(now)
    return True