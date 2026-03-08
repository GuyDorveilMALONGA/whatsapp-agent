"""
core/context_builder.py
L'innovation principale de Sëtu.
Le LLM ne reçoit jamais un message nu — il reçoit une situation complète.
C'est ce qui élimine les hallucinations.
V2 : injection mémoire réseau + profil usager enrichi
"""
from datetime import datetime, timezone
from db import queries
from agent.extractor import get_arrets_ligne, VALID_LINES
from memory import user_memory, network_memory


def build_context(
    message: str,
    intent: str,
    contact: dict,
    ligne: str | None = None,
    arret: str | None = None,
    signalements: list | None = None,
    history: list | None = None,
) -> str:
    """
    Construit le bloc de contexte injecté dans le prompt LLM.
    """
    blocks = []

    # ── [INTENTION] ───────────────────────────────────────
    blocks.append(f"[INTENTION DÉTECTÉE] {intent}")
    blocks.append(f"[MESSAGE USAGER] {message}")

    # ── [CONTEXTE CONVERSATION] ───────────────────────────
    # Si pas de ligne dans le message actuel → cherche dans l'historique
    if not ligne and history:
        ligne = _extract_ligne_from_history(history)
        if ligne:
            blocks.append(f"[CONTEXTE] Ligne {ligne} mentionnée précédemment dans la conversation.")

    # ── [RÉSEAU] ──────────────────────────────────────────
    if ligne:
        if ligne in VALID_LINES:
            arrets_info = get_arrets_ligne(ligne)
            blocks.append(
                f"[LIGNE] Bus {ligne} — {arrets_info.get('description', '')} "
                f"({len(arrets_info.get('aller', []))} arrêts)"
            )
        else:
            blocks.append(
                f"[LIGNE] La ligne '{ligne}' N'EXISTE PAS dans le réseau Dem Dikk. "
                f"Lignes disponibles : {', '.join(sorted(VALID_LINES))}"
            )

    # ── [SIGNALEMENTS ACTIFS] ─────────────────────────────
    if signalements is not None:
        if signalements:
            now = datetime.now(timezone.utc)
            sig_lines = []
            for s in signalements[:3]:
                try:
                    # colonne correcte : timestamp (pas created_at)
                    created = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
                    minutes_ago = int((now - created).total_seconds() / 60)
                    sig_lines.append(f"  → {s['position']} il y a {minutes_ago} min")  # position, pas arret_nom
                except Exception:
                    sig_lines.append(f"  → {s.get('position', '?')}")
            blocks.append(f"[SIGNALEMENTS ACTIFS bus {ligne}]\n" + "\n".join(sig_lines))
        else:
            blocks.append(f"[SIGNALEMENTS] Aucun signalement récent pour le bus {ligne}.")

    # ── [ARRÊT] ───────────────────────────────────────────
    if arret:
        blocks.append(f"[ARRÊT MENTIONNÉ] {arret}")

    # ── [USAGER] ──────────────────────────────────────────
    langue = contact.get("langue", "fr")
    fiabilite = contact.get("fiabilite_score", 0.5)
    profil_summary = user_memory.get_profil_summary(contact)
    blocks.append(
        f"[USAGER] Langue: {langue} | "
        f"Fiabilité: {fiabilite:.0%}"
        + (f" | {profil_summary}" if profil_summary else "")
    )

    # ── [MÉMOIRE RÉSEAU] V2 ───────────────────────────────
    if ligne and ligne in VALID_LINES:
        try:
            eta = network_memory.get_eta_prediction(ligne)
            mem_ctx = network_memory.format_for_context(eta)
            if mem_ctx:
                blocks.append(mem_ctx)
        except Exception:
            pass

    return "\n".join(blocks)


def _extract_ligne_from_history(history: list) -> str | None:
    """
    Cherche la dernière ligne mentionnée dans l'historique de conversation.
    Permet à Sëtu de comprendre 'et le 16 ?' après avoir parlé du 15.
    """
    from agent.extractor import _find_ligne, _normalize_text
    for msg in reversed(history):
        content = msg.get("content", "")
        normalized = _normalize_text(content)
        ligne, _ = _find_ligne(normalized.upper())
        if ligne:
            return ligne
    return None