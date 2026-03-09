"""
skills/abonnement.py — V4
Crée un abonnement en utilisant les entités LLM.
Découplé de extractor.py — architecture V5 complète.
"""
import re
import logging
from db import queries

logger = logging.getLogger(__name__)

_VALID_LINES = {
    "1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "15", "16A", "16B",
    "18", "20", "23", "121", "208", "213", "217", "218", "219", "220", "221", "227",
    "232", "233", "234", "311", "319", "327", "TO1", "501", "502", "503", "TAF TAF", "RUF-YENNE"
}


def _extract_heure(text: str) -> str | None:
    match = re.search(r'\b(\d{1,2})[h:](\d{0,2})\b', text, re.IGNORECASE)
    if match:
        h = match.group(1).zfill(2)
        m = match.group(2).zfill(2) if match.group(2) else "00"
        return f"{h}:{m}"
    return None


async def handle(message: str, contact: dict, langue: str, entities: dict) -> str:
    phone = contact["phone"]

    # Entités depuis le LLM — plus d'extraction regex
    ligne = entities.get("ligne")
    arret = entities.get("origin") or entities.get("destination") or ""

    if not ligne or str(ligne).upper() not in _VALID_LINES:
        ligne_str = ligne or "?"
        valides = ", ".join(sorted(_VALID_LINES)[:10]) + "..."
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