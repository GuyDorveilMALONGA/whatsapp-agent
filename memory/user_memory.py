"""
memory/user_memory.py — V2
Enrichit silencieusement le profil usager après chaque interaction.
Pas de formulaire, pas de question — Sëtu apprend en observant.

Champs mis à jour :
  - langue (détectée)
  - lignes_mentionnées (compteur)
  - arrêts_fréquents (compteur)
  - horaires_habituels (plages)
  - fiabilité_score (bayésien)
  - prénom_détecté (si l'usager se présente)
"""
import re
import json
import logging
from datetime import datetime, timezone

from db.client import get_client

logger = logging.getLogger(__name__)


# ── Mise à jour après chaque message ─────────────────────

def update_after_message(
    contact: dict,
    langue: str,
    intent: str,
    ligne: str | None = None,
    arret: str | None = None,
    signalement_confirme: bool = False,
):
    """
    Met à jour le profil_json du contact de façon non-bloquante.
    Appelé en fire-and-forget depuis main.py.
    """
    try:
        profil = contact.get("profil_json") or {}
        if isinstance(profil, str):
            profil = json.loads(profil)

        changed = False

        # Prénom détecté
        prenom = _extract_prenom(contact.get("_last_message", ""))
        if prenom and not profil.get("prenom"):
            profil["prenom"] = prenom
            changed = True

        # Langue
        if profil.get("langue") != langue:
            profil["langue"] = langue
            changed = True

        # Lignes mentionnées
        if ligne:
            lignes = profil.get("lignes_mentionnees", {})
            lignes[ligne] = lignes.get(ligne, 0) + 1
            profil["lignes_mentionnees"] = lignes
            changed = True

        # Arrêts fréquents
        if arret:
            arrets = profil.get("arrets_frequents", {})
            arrets[arret] = arrets.get(arret, 0) + 1
            profil["arrets_frequents"] = arrets
            changed = True

        # Horaires habituels
        heure = datetime.now(timezone.utc).strftime("%H")
        horaires = profil.get("horaires_habituels", {})
        horaires[heure] = horaires.get(heure, 0) + 1
        profil["horaires_habituels"] = horaires
        changed = True

        # Score de fiabilité (bayésien simple)
        if intent == "signalement":
            ancien_score = contact.get("fiabilite_score", 0.5)
            nb_signalements = profil.get("nb_signalements", 0) + 1
            nb_confirmes = profil.get("nb_confirmes", 0) + (1 if signalement_confirme else 0)
            # Prior bayésien : 0.5, mis à jour avec les observations
            nouveau_score = (1 + nb_confirmes) / (2 + nb_signalements)
            profil["nb_signalements"] = nb_signalements
            profil["nb_confirmes"] = nb_confirmes
            changed = True

            if abs(nouveau_score - ancien_score) > 0.01:
                _update_fiabilite(contact["id"], nouveau_score)

        if changed:
            _save_profil(contact["id"], profil)

    except Exception as e:
        logger.error(f"[UserMemory] Erreur update: {e}")


def get_profil_summary(contact: dict) -> str:
    """
    Retourne un résumé du profil pour le context_builder.
    """
    profil = contact.get("profil_json") or {}
    if isinstance(profil, str):
        try:
            profil = json.loads(profil)
        except Exception:
            return ""

    parts = []

    prenom = profil.get("prenom")
    if prenom:
        parts.append(f"Prénom: {prenom}")

    # Ligne favorite (la plus mentionnée)
    lignes = profil.get("lignes_mentionnees", {})
    if lignes:
        fav = max(lignes, key=lignes.get)
        parts.append(f"Ligne favorite: Bus {fav} ({lignes[fav]}x)")

    # Arrêt favori
    arrets = profil.get("arrets_frequents", {})
    if arrets:
        fav_arret = max(arrets, key=arrets.get)
        parts.append(f"Arrêt habituel: {fav_arret}")

    # Heure habituelle
    horaires = profil.get("horaires_habituels", {})
    if horaires:
        heure_fav = max(horaires, key=horaires.get)
        parts.append(f"Heure habituelle: {heure_fav}h")

    # Fiabilité
    fiab = contact.get("fiabilite_score", 0.5)
    parts.append(f"Fiabilité: {fiab:.0%}")

    return " | ".join(parts) if parts else ""


# ── Fonctions DB ──────────────────────────────────────────

def _save_profil(contact_id: str, profil: dict):
    db = get_client()
    db.table("contacts").update({"profil_json": profil}).eq("id", contact_id).execute()


def _update_fiabilite(contact_id: str, score: float):
    db = get_client()
    db.table("contacts").update({"fiabilite_score": round(score, 3)}).eq("id", contact_id).execute()


# ── Helpers ───────────────────────────────────────────────

_PRENOM_PATTERNS = [
    r"\bje\s+m[' ]appelle\s+(\w+)",
    r"\bmon\s+nom\s+est\s+(\w+)",
    r"\bc[' ]est\s+(\w+)\s+ici",
    r"\bmaa\s+ngi\s+tudd\s+(\w+)",   # wolof : "maa ngi tudd X"
]

def _extract_prenom(text: str) -> str | None:
    if not text:
        return None
    for pattern in _PRENOM_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            prenom = m.group(1).capitalize()
            if len(prenom) >= 2:
                return prenom
    return None
