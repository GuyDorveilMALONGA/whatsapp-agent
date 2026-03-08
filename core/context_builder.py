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

    # ── [RÉSEAU] ─────────────────────────────────────────
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

    # ── [SIGNALEMENTS ACTIFS] ────────────────────────────
    if signalements is not None:
        if signalements:
            now = datetime.now(timezone.utc)
            sig_lines = []
            for s in signalements[:3]:  # max 3 signalements
                try:
                    created = datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
                    minutes_ago = int((now - created).total_seconds() / 60)
                    sig_lines.append(f"  → {s['arret_nom']} il y a {minutes_ago} min")
                except Exception:
                    sig_lines.append(f"  → {s['arret_nom']}")
            blocks.append(f"[SIGNALEMENTS ACTIFS bus {ligne}]\n" + "\n".join(sig_lines))
        else:
            blocks.append(f"[SIGNALEMENTS] Aucun signalement récent pour le bus {ligne}.")

    # ── [ARRÊT] ───────────────────────────────────────────
    if arret:
        blocks.append(f"[ARRÊT MENTIONNÉ] {arret}")

    # ── [USAGER] ─────────────────────────────────────────
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
        eta = network_memory.get_eta_prediction(ligne)
        mem_ctx = network_memory.format_for_context(eta)
        if mem_ctx:
            blocks.append(mem_ctx)

    return "\n".join(blocks)
