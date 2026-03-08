"""
core/session_manager.py — V2
Deux responsabilités :
1. Lock par téléphone — no race conditions (existant)
2. État conversationnel — gère les flows multi-tours (nouveau)

États possibles :
- None          : conversation normale
- "attente_arret" : Sëtu attend que l'usager donne son arrêt
                    (après avoir trouvé un signalement)
"""
import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── TTL ───────────────────────────────────────────────────
SESSION_TTL_SECONDS = 1800       # 30 min inactivité → cleanup
CONTEXT_TTL_SECONDS = 120        # 2 min → si pas de réponse, on abandonne le flow


# ── Modèle d'état ─────────────────────────────────────────

@dataclass
class SessionContext:
    """État conversationnel d'une session."""
    etat: str | None = None          # None | "attente_arret"
    ligne: str | None = None         # ligne en cours de discussion
    signalement: dict | None = None  # signalement trouvé en attente
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return elapsed > CONTEXT_TTL_SECONDS

    def reset(self):
        self.etat = None
        self.ligne = None
        self.signalement = None
        self.timestamp = datetime.now(timezone.utc)


# ── Stockage ──────────────────────────────────────────────

_sessions: dict[str, asyncio.Lock] = {}
_contexts: dict[str, SessionContext] = {}
_last_seen: dict[str, datetime] = {}


# ── Lock (existant) ───────────────────────────────────────

def get_session_lock(phone: str) -> asyncio.Lock:
    if phone not in _sessions:
        _sessions[phone] = asyncio.Lock()
        logger.debug(f"[Session] Nouvelle session : {phone[-4:]}")
    _last_seen[phone] = datetime.now(timezone.utc)
    return _sessions[phone]


# ── Contexte (nouveau) ────────────────────────────────────

def get_context(phone: str) -> SessionContext:
    """Retourne le contexte de la session, crée-le si absent."""
    if phone not in _contexts:
        _contexts[phone] = SessionContext()
    ctx = _contexts[phone]
    # Si expiré → reset automatique
    if ctx.etat and ctx.is_expired():
        logger.debug(f"[Session] Contexte expiré pour {phone[-4:]} — reset")
        ctx.reset()
    return ctx


def set_attente_arret(phone: str, ligne: str, signalement: dict):
    """
    Passe la session en état 'attente_arret'.
    Sëtu vient de trouver un signalement et attend que l'usager
    donne son arrêt pour calculer la distance.
    """
    ctx = get_context(phone)
    ctx.etat = "attente_arret"
    ctx.ligne = ligne
    ctx.signalement = signalement
    ctx.timestamp = datetime.now(timezone.utc)
    logger.debug(f"[Session] {phone[-4:]} → attente_arret (bus {ligne})")


def reset_context(phone: str):
    """Remet la session en état normal après résolution du flow."""
    ctx = get_context(phone)
    ctx.reset()
    logger.debug(f"[Session] {phone[-4:]} → reset")


def is_waiting_for_arret(phone: str) -> bool:
    """True si Sëtu attend la réponse d'arrêt de cet usager."""
    ctx = get_context(phone)
    return ctx.etat == "attente_arret" and not ctx.is_expired()


# ── Cleanup ───────────────────────────────────────────────

def cleanup_inactive_sessions():
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
        _contexts.pop(phone, None)
        _last_seen.pop(phone, None)

    if to_delete:
        logger.info(f"[Session] {len(to_delete)} session(s) nettoyée(s)")


def active_session_count() -> int:
    return len(_sessions)