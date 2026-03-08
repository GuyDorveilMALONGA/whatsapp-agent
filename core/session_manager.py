"""
core/session_manager.py — V3 (Supabase + fallback mémoire)

Deux responsabilités :
1. Lock par téléphone — no race conditions (asyncio, en mémoire)
2. État conversationnel — persisté dans Supabase avec fallback mémoire
   si Supabase est lent ou timeout (faille 2 réglée)

États :
- None             : conversation normale
- "attente_arret"  : attend l'arrêt de l'usager (flow question)
- "attente_origin" : attend l'arrêt de départ (flow itinéraire)
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from db import queries

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS  = 1800   # 30 min → cleanup locks
CONTEXT_TTL_SECONDS  = 120    # 2 min → TTL session


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
# Locks : toujours en mémoire (protègent les requêtes concurrentes)
# Contextes : Supabase en priorité, mémoire en fallback

_locks:    dict[str, asyncio.Lock]   = {}
_fallback: dict[str, SessionContext] = {}  # cache mémoire si Supabase KO
_last_seen: dict[str, datetime]      = {}


# ── Lock ──────────────────────────────────────────────────

def get_session_lock(phone: str) -> asyncio.Lock:
    if phone not in _locks:
        _locks[phone] = asyncio.Lock()
    _last_seen[phone] = datetime.now(timezone.utc)
    return _locks[phone]


# ── Lecture (Supabase → fallback mémoire) ─────────────────

def get_context(phone: str) -> SessionContext:
    """
    Lit depuis Supabase en priorité.
    Si Supabase échoue → fallback sur le cache mémoire local.
    Jamais de False silencieux (faille 2 réglée).
    """
    try:
        row = queries.get_session(phone)
        if row:
            ctx = SessionContext(
                etat=row.get("etat"),
                ligne=row.get("ligne"),
                signalement=row.get("signalement"),
                destination=row.get("destination"),
            )
            # Sync le fallback mémoire
            _fallback[phone] = ctx
            return ctx
        # Pas de session Supabase → nettoie le fallback aussi
        _fallback.pop(phone, None)
        return SessionContext()

    except Exception as e:
        logger.error(f"[Session] Supabase KO, fallback mémoire pour {phone[-4:]}: {e}")
        # Fallback mémoire
        ctx = _fallback.get(phone, SessionContext())
        if ctx.etat and ctx.is_expired():
            _fallback.pop(phone, None)
            return SessionContext()
        return ctx


# ── Setters ───────────────────────────────────────────────

def set_attente_arret(phone: str, ligne: str, signalement: dict):
    """Passe en état 'attente_arret' — écrit Supabase + fallback."""
    ctx = SessionContext(etat="attente_arret", ligne=ligne, signalement=signalement)
    _fallback[phone] = ctx
    try:
        queries.set_session(phone=phone, etat="attente_arret",
                            ligne=ligne, signalement=signalement)
        logger.debug(f"[Session] {phone[-4:]} → attente_arret (bus {ligne})")
    except Exception as e:
        logger.error(f"[Session] set_attente_arret Supabase KO (fallback actif): {e}")


def set_attente_origin(phone: str, destination: str):
    """Passe en état 'attente_origin' — écrit Supabase + fallback."""
    ctx = SessionContext(etat="attente_origin", destination=destination)
    _fallback[phone] = ctx
    try:
        queries.set_session(phone=phone, etat="attente_origin", destination=destination)
        logger.debug(f"[Session] {phone[-4:]} → attente_origin (dest: {destination})")
    except Exception as e:
        logger.error(f"[Session] set_attente_origin Supabase KO (fallback actif): {e}")


def reset_context(phone: str):
    """Reset session — supprime Supabase + fallback."""
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
    """True si l'usager est dans n'importe quel flow multi-tour."""
    return get_context(phone).etat is not None


# ── Abandon de flow ───────────────────────────────────────

_ABANDON_PATTERNS = [
    r"\b(laisse\s+tomber|annule|stop|arrête|oublie|non merci|pas grave|ça va)\b",
    r"\b(cancel|nevermind|forget\s+it|nvm)\b",
    r"\b(dafa\s+nii|sëde\s+ko|nii\s+rekk)\b",   # wolof
]

import re

def is_abandon(text: str) -> bool:
    """
    Détecte si l'usager veut abandonner le flow en cours.
    Ex: "laisse tomber", "annule", "stop", "non merci"
    """
    t = text.lower().strip()
    for pattern in _ABANDON_PATTERNS:
        if re.search(pattern, t):
            return True
    return False


# ── Cleanup locks inactifs ────────────────────────────────

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