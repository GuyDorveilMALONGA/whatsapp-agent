"""
core/session_manager.py — V3.1
État conversationnel persisté dans Supabase + fallback mémoire.

FIX #4 : TTL session 10 minutes (was 2 minutes)
→ Un usager qui reçoit un appel entre deux messages
  ne perd plus son contexte de flow.
"""
import asyncio
import re
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from db import queries

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS  = 1800   # 30 min → cleanup locks
CONTEXT_TTL_SECONDS  = 600    # FIX #4 : 10 min (was 120s = 2min)


# ── Modèle ────────────────────────────────────────────────

@dataclass
class SessionContext:
    etat:        str | None  = None
    ligne:       str | None  = None
    signalement: dict | None = None
    destination: str | None  = None
    _expires:    datetime    = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=CONTEXT_TTL_SECONDS)
    )

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self._expires


# ── Stockage ──────────────────────────────────────────────

_locks:    dict[str, asyncio.Lock]   = {}
_fallback: dict[str, SessionContext] = {}
_last_seen: dict[str, datetime]      = {}


# ── Lock ──────────────────────────────────────────────────

def get_session_lock(phone: str) -> asyncio.Lock:
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    _last_seen[phone] = datetime.now(timezone.utc)
    return _locks[phone]


# ── Lecture ───────────────────────────────────────────────

def get_context(phone: str) -> SessionContext:
    try:
        row = queries.get_session(phone)
        if row:
            ctx = SessionContext(
                etat=row.get("etat"),
                ligne=row.get("ligne"),
                signalement=row.get("signalement"),
                destination=row.get("destination"),
            )
            _fallback[phone] = ctx
            return ctx
        _fallback.pop(phone, None)
        return SessionContext()
    except Exception as e:
        logger.error(f"[Session] Supabase KO, fallback mémoire pour {phone[-4:]}: {e}")
        ctx = _fallback.get(phone, SessionContext())
        if ctx.etat and ctx.is_expired():
            _fallback.pop(phone, None)
            return SessionContext()
        return ctx


# ── Setters ───────────────────────────────────────────────

def set_attente_arret(phone: str, ligne: str, signalement: dict):
    ctx = SessionContext(etat="attente_arret", ligne=ligne, signalement=signalement)
    _fallback[phone] = ctx
    try:
        queries.set_session(phone=phone, etat="attente_arret",
                            ligne=ligne, signalement=signalement)
        logger.debug(f"[Session] {phone[-4:]} → attente_arret (bus {ligne})")
    except Exception as e:
        logger.error(f"[Session] set_attente_arret Supabase KO (fallback actif): {e}")


def set_attente_origin(phone: str, destination: str):
    ctx = SessionContext(etat="attente_origin", destination=destination)
    _fallback[phone] = ctx
    try:
        queries.set_session(phone=phone, etat="attente_origin", destination=destination)
        logger.debug(f"[Session] {phone[-4:]} → attente_origin (dest: {destination})")
    except Exception as e:
        logger.error(f"[Session] set_attente_origin Supabase KO (fallback actif): {e}")


def reset_context(phone: str):
    _fallback.pop(phone, None)
    try:
        queries.delete_session(phone)
        logger.debug(f"[Session] {phone[-4:]} → reset")
    except Exception as e:
        logger.error(f"[Session] reset_context Supabase KO: {e}")


# ── Checkers ──────────────────────────────────────────────

def is_waiting_for_arret(phone: str) -> bool:
    return get_context(phone).etat == "attente_arret"


def is_waiting_for_origin(phone: str) -> bool:
    return get_context(phone).etat == "attente_origin"


def is_in_flow(phone: str) -> bool:
    return get_context(phone).etat is not None


# ── Abandon ───────────────────────────────────────────────

_ABANDON_PATTERNS = [
    r"\b(laisse\s+tomber|annule|stop|arrête|oublie|non merci|pas grave|ça va)\b",
    r"\b(cancel|nevermind|forget\s+it|nvm)\b",
    r"\b(dafa\s+nii|sëde\s+ko|nii\s+rekk)\b",
]


def is_abandon(text: str) -> bool:
    t = text.lower().strip()
    for pattern in _ABANDON_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


# ── Cleanup ───────────────────────────────────────────────

def cleanup_inactive_sessions():
    now = datetime.now(timezone.utc)
    to_delete = [
        phone for phone, last in _last_seen.items()
        if (now - last).total_seconds() > SESSION_TTL_SECONDS
        and not _locks.get(phone, asyncio.Lock()).locked()
    ]
    for phone in to_delete:
        _locks.pop(phone, None)
        _fallback.pop(phone, None)
        _last_seen.pop(phone, None)
    if to_delete:
        logger.info(f"[Session] {len(to_delete)} lock(s) nettoyé(s)")


def active_session_count() -> int:
    return len(_locks)
