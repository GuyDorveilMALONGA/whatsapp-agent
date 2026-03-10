"""
skills/abonnement.py — V5.0
Crée un abonnement en utilisant les entités LLM.

MIGRATIONS V5.0 depuis V4 :
  - FIX B10 : VALID_LINES importé depuis config.settings (source unique)
    Plus de set dupliqué qui se désynchronise.
"""
import re
import logging
from db import queries
from config.settings import VALID_LINES  # FIX B10 : source unique

logger = logging.getLogger(__name__)


def _extract_heure(text: str) -> str | None:
    match = re.search(r'\b(\d{1,2})[h:](\d{0,2})\b', text, re.IGNORECASE)
    if match:
        h = match.group(1).zfill(2)
        m = match.group(2).zfill(2) if match.group(2) else "00"
        return f"{h}:{m}"
    return None


async def handle(message: str, contact: dict, langue: str, entities: dict) -> str:
    phone = contact["phone"]

    ligne = entities.get("ligne")
    arret = entities.get("origin") or entities.get("destination") or ""

    if not ligne or str(ligne).upper() not in VALID_LINES:
        ligne_str = ligne or "?"
        valides = ", ".join(sorted(VALID_LINES, key=lambda x: (len(x), x))[:10]) + "..."
        if langue == "wolof":
            return (f"Ligne {ligne_str} — duma ko xam ci réseau Dem Dikk yi. "
                    f"Wax ma numéro bus bi.")
        return (f"❌ La ligne *{ligne_str}* n'existe pas.\n"
                f"Lignes disponibles : {valides}")

    ligne = str(ligne).upper()
    heure = _extract_heure(message)

    try:
        queries.create_abonnement(phone, ligne, arret, heure)
    except Exception as e:
        logger.error(f"[Abonnement] Erreur DB: {e}")
        return "❌ Une erreur technique m'empêche de créer l'alerte. Réessaie plus tard."

    arret_str = f" près de *{arret}*" if arret else ""
    heure_str = f" à *{heure}*" if heure else ""

    if langue == "wolof":
        return (f"🔔 Waaw ! Bus {ligne}{arret_str} — maa ngiy gis. "
                f"Dinaa la wéer bu ñu ko signalé. 🙏")
    return (f"🔔 C'est noté ! Je t'alerterai dès que le Bus *{ligne}* "
            f"est signalé{arret_str}{heure_str}. 🙏")