"""
agent/intent_cache.py
Cache d'intention — évite les appels LLM répétitifs.

FIX #3 : Cache key = hash(message + état session)
→ évite le bug "liberté 5" = signalement en cache
  alors que dans un flow attente_arret c'est une réponse.
"""
import hashlib
import time
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

_TTL_SECONDS = 7 * 24 * 3600  # 7 jours
_MAX_SIZE    = 1000
_cache: OrderedDict = OrderedDict()  # key → (intent, timestamp)


def _hash(text: str, session_state: str | None = None) -> str:
    """
    Clé = hash(message normalisé + état session).
    Sans état session → même comportement qu'avant.
    Avec état → évite les collisions de contexte.
    """
    raw = text.strip().lower()
    if session_state:
        raw = f"{session_state}::{raw}"
    return hashlib.md5(raw.encode()).hexdigest()


def get(normalized_text: str, session_state: str | None = None) -> str | None:
    """
    Retourne l'intent caché ou None si absent/expiré.
    session_state : 'attente_arret' | 'attente_origin' | None
    """
    key   = _hash(normalized_text, session_state)
    entry = _cache.get(key)
    if not entry:
        return None
    intent, ts = entry
    if time.time() - ts > _TTL_SECONDS:
        del _cache[key]
        return None
    _cache.move_to_end(key)
    return intent


def set(normalized_text: str, intent: str, session_state: str | None = None):
    """
    Stocke un intent dans le cache.
    session_state : état de session au moment du routage.
    """
    key = _hash(normalized_text, session_state)
    _cache[key] = (intent, time.time())
    _cache.move_to_end(key)
    if len(_cache) > _MAX_SIZE:
        _cache.popitem(last=False)
    logger.debug(f"[IntentCache] SET [{session_state or 'no_state'}] {normalized_text[:30]} → {intent}")


def stats() -> dict:
    return {"size": len(_cache), "max": _MAX_SIZE}
