"""
core/context_builder.py — V5 (LLM-Native)
L'innovation principale de Xëtu.
Le LLM ne reçoit jamais un message nu — il reçoit une situation complète.

V5 : chargement JSON supprimé — source unique : core.network (singleton)
"""
import re
import logging
from datetime import datetime, timezone
from memory import user_memory, network_memory
from core.network import NETWORK, VALID_LINES

logger = logging.getLogger(__name__)


def build_context(
    message: str,
    intent: str,
    contact: dict,
    ligne: str | None = None,
    arret: str | None = None,
    signalements: list | None = None,
    history: list | None = None,
    entities: dict | None = None,
) -> str:
    blocks = []
    entities = entities or {}

    # Consolidation : entities LLM prioritaires sur paramètres directs
    ligne = ligne or entities.get("ligne")
    arret = arret or entities.get("origin") or entities.get("destination")

    # ── [INTENTION] ───────────────────────────────────────
    blocks.append(f"[INTENTION DÉTECTÉE] {intent}")
    blocks.append(f"[MESSAGE USAGER] {message}")

    # ── [CONTEXTE CONVERSATION] ───────────────────────────
    if not ligne and history:
        ligne_historique = _extract_ligne_from_history(history)
        if ligne_historique:
            ligne = ligne_historique
            blocks.append(
                f"[CONTEXTE] Ligne {ligne} mentionnée précédemment dans la conversation."
            )

    # ── [RÉSEAU] ──────────────────────────────────────────
    if ligne:
        ligne = str(ligne).upper()
        if ligne in VALID_LINES:
            info  = NETWORK.get(ligne, {})
            stops = info.get("stops", [])
            desc  = info.get("name", info.get("description", ""))
            blocks.append(
                f"[LIGNE] Bus {ligne} — {desc} ({len(stops)} arrêts au total)"
            )
        else:
            valides = ", ".join(sorted(VALID_LINES)[:15]) + "..."
            blocks.append(
                f"[LIGNE] La ligne '{ligne}' N'EXISTE PAS dans le réseau Dem Dikk. "
                f"Lignes disponibles : {valides}"
            )

    # ── [SIGNALEMENTS ACTIFS] ─────────────────────────────
    if signalements is not None:
        if signalements:
            now      = datetime.now(timezone.utc)
            sig_lines = []
            for s in signalements[:3]:
                try:
                    created     = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
                    minutes_ago = int((now - created).total_seconds() / 60)
                    sig_lines.append(f"  → {s['position']} il y a {minutes_ago} min")
                except Exception:
                    sig_lines.append(f"  → {s.get('position', '?')}")
            blocks.append(
                f"[SIGNALEMENTS ACTIFS bus {ligne}]\n" + "\n".join(sig_lines)
            )
        else:
            blocks.append(
                f"[SIGNALEMENTS] Aucun signalement récent pour le bus {ligne}."
            )

    # ── [ARRÊT] ───────────────────────────────────────────
    if arret:
        blocks.append(f"[ARRÊT MENTIONNÉ] {arret}")

    # ── [USAGER] ──────────────────────────────────────────
    langue        = contact.get("langue", "fr")
    fiabilite     = contact.get("fiabilite_score", 0.5)
    profil_summary = user_memory.get_profil_summary(contact)
    blocks.append(
        f"[USAGER] Langue: {langue} | Fiabilité: {fiabilite:.0%}"
        + (f" | {profil_summary}" if profil_summary else "")
    )

    # ── [MÉMOIRE RÉSEAU] ──────────────────────────────────
    if ligne and ligne in VALID_LINES:
        try:
            eta     = network_memory.get_eta_prediction(ligne)
            mem_ctx = network_memory.format_for_context(eta)
            if mem_ctx:
                blocks.append(mem_ctx)
        except Exception:
            pass

    return "\n".join(blocks)


def _extract_ligne_from_history(history: list) -> str | None:
    """
    Cherche la dernière ligne mentionnée dans l'historique.
    Permet à Xëtu de comprendre 'et le 16 ?' après avoir parlé du 15.
    """
    for msg in reversed(history):
        content = msg.get("content", "")
        match = re.search(
            r'\b(?:bus|ligne)?\s*(\d{1,3}[A-Z]?|TO1|TAF\s*TAF)\b',
            content, re.IGNORECASE
        )
        if match:
            ligne = match.group(1).upper()
            if ligne in VALID_LINES:
                return ligne
    return None