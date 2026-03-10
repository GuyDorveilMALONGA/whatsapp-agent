"""
core/session_manager.py — V5.0
État conversationnel 100% persisté dans Supabase.

MIGRATIONS V5.0 depuis V4.1 :
  - FIX SE2 : cleanup_inactive_sessions ne crée plus de locks fantômes
  - FIX SE3 : TTL locks aligné sur TTL DB (10 min)
  - set_session() inchangé (déjà correct en V4.1)
"""
import asyncio
import re
import logging
from datetime import datetime, timezone
from dataclasses import dataclass

from db import queries

logger = logging.getLogger(__name__)

# FIX SE3 : aligné sur SESSION_CONTEXT_TTL_SECONDS de queries.py (600s = 10 min)
SESSION_TTL_SECONDS = 600


# ── Modèle ────────────────────────────────────────────────

@dataclass
class SessionContext:
    etat:        str | None  = None
    ligne:       str | None  = None
    signalement: dict | None = None
    destination: str | None  = None


# ── Verrous asyncio (À migrer vers Redis si 2+ instances) ─

_locks:     dict[str, asyncio.Lock] = {}
_last_seen: dict[str, datetime]     = {}


def get_session_lock(phone: str) -> asyncio.Lock:
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    _last_seen[phone] = datetime.now(timezone.utc)
    return _locks[phone]


# ── Lecture — source de vérité unique : Supabase ──────────

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
            phone=phone,
            etat=etat,
            ligne=ligne,
            destination=destination,
            signalement=signalement,
        )
        logger.debug(
            f"[Session] {phone[-4:]} → set_session "
            f"(etat={etat}, ligne={ligne}, dest={destination})"
        )
    except Exception as e:
        logger.error(f"[Session] set_session Supabase KO: {e}")


def set_attente_arret(phone: str, ligne: str, signalement: dict):
    try:
        queries.set_session(
            phone=phone,
            etat="attente_arret",
            ligne=ligne,
            signalement=signalement,
        )
        logger.debug(f"[Session] {phone[-4:]} → attente_arret (bus {ligne})")
    except Exception as e:
        logger.error(f"[Session] set_attente_arret Supabase KO: {e}")


def set_attente_origin(phone: str, destination: str):
    try:
        queries.set_session(
            phone=phone,
            etat="attente_origin",
            destination=destination,
        )
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


# ── Cleanup — FIX SE2 : ne crée plus de locks fantômes ───

def cleanup_inactive_sessions():
    now = datetime.now(timezone.utc)
    to_delete = []
    for phone, last in _last_seen.items():
        if (now - last).total_seconds() > SESSION_TTL_SECONDS:
            lock = _locks.get(phone)
            # FIX SE2 : vérifier que le lock EXISTE avant de tester .locked()
            if lock is not None and not lock.locked():
                to_delete.append(phone)

    for phone in to_delete:
        _locks.pop(phone, None)
        _last_seen.pop(phone, None)
    if to_delete:
        logger.info(f"[Session] {len(to_delete)} lock(s) asyncio nettoyé(s)")


def active_session_count() -> int:
    return len(_locks)