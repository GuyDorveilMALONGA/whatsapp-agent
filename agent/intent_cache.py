"""
agent/intent_cache.py
Cache d'intention — évite les appels LLM répétitifs.
V1 : cache in-memory (TTL 7 jours simulé par taille max)
V2 : swap Redis en changeant uniquement ce fichier
"""
import hashlib
import time
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)

# Cache LRU in-memory : max 1000 entrées, TTL 7 jours
_TTL_SECONDS = 7 * 24 * 3600
_MAX_SIZE = 1000
_cache: OrderedDict = OrderedDict()  # key → (intent, timestamp)


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def get(normalized_text: str) -> str | None:
    """Retourne l'intent caché ou None si absent/expiré."""
    key = _hash(normalized_text)
    entry = _cache.get(key)
    if not entry:
        return None
    intent, ts = entry
    if time.time() - ts > _TTL_SECONDS:
        del _cache[key]
        return None
    # LRU : déplace en fin
    _cache.move_to_end(key)
    return intent


def set(normalized_text: str, intent: str):
    """Stocke un intent dans le cache."""
    key = _hash(normalized_text)
    _cache[key] = (intent, time.time())
    _cache.move_to_end(key)
    # Éviction LRU si trop grand
    if len(_cache) > _MAX_SIZE:
        _cache.popitem(last=False)
    logger.debug(f"[IntentCache] SET {normalized_text[:30]} → {intent}")


def stats() -> dict:
    return {"size": len(_cache), "max": _MAX_SIZE}
