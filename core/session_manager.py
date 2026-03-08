"""
core/session_manager.py — V2
Garde une session active par numéro de téléphone.
Si un usager envoie 2 messages rapidement, ils sont traités en séquence,
jamais en parallèle. Élimine les écritures concurrentes sur Supabase.
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Dict global : phone → asyncio.Lock
_sessions: dict[str, asyncio.Lock] = {}
# Timestamp dernier message par session (pour cleanup)
_last_seen: dict[str, datetime] = {}

# Durée max d'inactivité avant suppression de la session (30 min)
SESSION_TTL_SECONDS = 1800


def get_session_lock(phone: str) -> asyncio.Lock:
    """
    Retourne le lock associé à ce numéro de téléphone.
    Crée-le s'il n'existe pas encore.
    """
    if phone not in _sessions:
        _sessions[phone] = asyncio.Lock()
        logger.debug(f"[Session] Nouvelle session : {phone[-4:]}")

    _last_seen[phone] = datetime.now(timezone.utc)
    return _sessions[phone]


def cleanup_inactive_sessions():
    """
    Supprime les sessions inactives depuis plus de SESSION_TTL_SECONDS.
    Appelé par le heartbeat.
    """
    now = datetime.now(timezone.utc)
    to_delete = []

    for phone, last in _last_seen.items():
        elapsed = (now - last).total_seconds()
        if elapsed > SESSION_TTL_SECONDS:
            lock = _sessions.get(phone)
            if lock and not lock.locked():
                to_delete.append(phone)

    for phone in to_delete:
        _sessions.pop(phone, None)
        _last_seen.pop(phone, None)

    if to_delete:
        logger.info(f"[Session] {len(to_delete)} session(s) nettoyée(s)")


def active_session_count() -> int:
    return len(_sessions)
