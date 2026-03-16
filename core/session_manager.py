"""
core/session_manager.py — V6.0
État conversationnel 100% persisté dans Supabase.

MIGRATIONS V6.0 depuis V5.0 :
  - FIX BUG-C5 : Locks distribués via Redis pour multi-worker Railway.
    Les asyncio.Lock() en mémoire locale sont brisés avec 2+ workers —
    chaque worker a son propre dict → sérialisation ignorée → doublons.
    Solution : redis.asyncio distributed lock avec fallback asyncio local
    si Redis est indisponible (dégradé mais fonctionnel sur 1 worker).
  - get_session_lock() retourne un objet avec .acquire()/.release() async.
  - queue_manager.py mis à jour pour utiliser la nouvelle interface.
  - cleanup_inactive_sessions() ne nettoie que les locks asyncio du fallback.
"""
import asyncio
import re
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from db import queries

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 600   # 10 min
_LOCK_TIMEOUT       = 30    # secondes max pour acquérir un lock


# ── Modèle ────────────────────────────────────────────────

@dataclass
class SessionContext:
    etat:        str | None  = None
    ligne:       str | None  = None
    signalement: dict | None = None
    destination: str | None  = None


# ══════════════════════════════════════════════════════════
# LOCKS DISTRIBUÉS — Redis avec fallback asyncio local
# ══════════════════════════════════════════════════════════

_redis_client  = None
_redis_failed  = False
_local_locks:  dict[str, asyncio.Lock] = {}
_last_seen:    dict[str, datetime]     = {}


def _get_redis():
    """Retourne le client Redis async, None si indisponible."""
    global _redis_client, _redis_failed
    if _redis_failed:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import os
        redis_url = os.environ.get("REDIS_URL") or os.environ.get("REDISCLOUD_URL")
        if not redis_url:
            _redis_failed = True
            logger.warning(
                "[Session] REDIS_URL absent — fallback asyncio.Lock (1 worker seulement). "
                "Ajoute Redis sur Railway pour le multi-worker."
            )
            return None
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(redis_url, decode_responses=True)
        logger.info("[Session] Redis connecté ✅ — locks distribués actifs")
        return _redis_client
    except Exception as e:
        _redis_failed = True
        logger.warning(f"[Session] Redis indisponible ({e}) — fallback asyncio.Lock")
        return None


class _RedisLock:
    """Distributed lock Redis via SET NX PX."""
    def __init__(self, redis, key: str):
        self._redis = redis
        self._key   = f"xetu:lock:{key}"
        self._token = None

    async def acquire(self) -> bool:
        import uuid, time
        self._token = str(uuid.uuid4())
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while time.monotonic() < deadline:
            ok = await self._redis.set(
                self._key, self._token,
                nx=True, px=SESSION_TTL_SECONDS * 1000
            )
            if ok:
                return True
            await asyncio.sleep(0.05)
        return False

    async def release(self):
        script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        else
            return 0
        end
        """
        try:
            await self._redis.eval(script, 1, self._key, self._token)
        except Exception as e:
            logger.warning(f"[Session] Redis release erreur: {e}")


class _LocalLock:
    """Wrapper asyncio.Lock pour interface uniforme avec _RedisLock."""
    def __init__(self, lock: asyncio.Lock):
        self._lock = lock

    async def acquire(self) -> bool:
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=_LOCK_TIMEOUT)
            return True
        except asyncio.TimeoutError:
            return False

    async def release(self):
        if self._lock.locked():
            self._lock.release()


def get_session_lock(phone: str):
    """
    Retourne un lock pour ce phone.
    Redis si disponible (multi-worker safe), asyncio sinon (1 worker).
    Interface : await lock.acquire() / await lock.release()
    """
    _last_seen[phone] = datetime.now(timezone.utc)
    redis = _get_redis()
    if redis:
        return _RedisLock(redis, phone)
    if phone not in _local_locks:
        _local_locks[phone] = asyncio.Lock()
    return _LocalLock(_local_locks[phone])


# ── Lecture ───────────────────────────────────────────────

def get_context(phone: str) -> SessionContext:
    try:
        row = queries.get_session(phone)
        if row:
            return SessionContext(
                etat=row.get("etat"),
                ligne=row.get("ligne"),
                signalement=row.get("signalement"),
                destination=row.get("destination"),
            )
    except Exception as e:
        logger.error(f"[Session] Supabase KO pour {phone[-4:]}: {e}")
    return SessionContext()


# ── Setters ───────────────────────────────────────────────

def set_session(phone: str,
                etat: str | None = None,
                ligne: str | None = None,
                destination: str | None = None,
                signalement: dict | None = None):
    try:
        queries.set_session(
            phone=phone, etat=etat, ligne=ligne,
            destination=destination, signalement=signalement,
        )
        logger.debug(f"[Session] {phone[-4:]} → set_session (etat={etat}, ligne={ligne})")
    except Exception as e:
        logger.error(f"[Session] set_session Supabase KO: {e}")


def set_attente_arret(phone: str, ligne: str, signalement: dict):
    try:
        queries.set_session(phone=phone, etat="attente_arret",
                            ligne=ligne, signalement=signalement)
        logger.debug(f"[Session] {phone[-4:]} → attente_arret (bus {ligne})")
    except Exception as e:
        logger.error(f"[Session] set_attente_arret Supabase KO: {e}")


def set_attente_origin(phone: str, destination: str):
    try:
        queries.set_session(phone=phone, etat="attente_origin", destination=destination)
        logger.debug(f"[Session] {phone[-4:]} → attente_origin (dest: {destination})")
    except Exception as e:
        logger.error(f"[Session] set_attente_origin Supabase KO: {e}")


def reset_context(phone: str):
    try:
        queries.delete_session(phone)
        logger.debug(f"[Session] {phone[-4:]} → reset")
    except Exception as e:
        logger.error(f"[Session] reset_context Supabase KO: {e}")


# ── Abandon ───────────────────────────────────────────────

_ABANDON_PATTERNS = [
    r"\b(laisse\s+tomber|annule|stop|arrête|oublie|non merci|pas grave|ça va)\b",
    r"\b(cancel|nevermind|forget\s+it|nvm)\b",
    r"\b(dafa\s+nii|sëde\s+ko|nii\s+rekk)\b",
]


def is_abandon(text: str) -> bool:
    t = text.lower().strip()
    return any(re.search(pattern, t) for pattern in _ABANDON_PATTERNS)


# ── Cleanup locks locaux (fallback uniquement) ────────────

def cleanup_inactive_sessions():
    now = datetime.now(timezone.utc)
    to_delete = []
    for phone, last in _last_seen.items():
        if (now - last).total_seconds() > SESSION_TTL_SECONDS:
            lock = _local_locks.get(phone)
            if lock is not None and not lock.locked():
                to_delete.append(phone)
    for phone in to_delete:
        _local_locks.pop(phone, None)
        _last_seen.pop(phone, None)
    if to_delete:
        logger.info(f"[Session] {len(to_delete)} lock(s) locaux nettoyés")


def active_session_count() -> int:
    return len(_local_locks)