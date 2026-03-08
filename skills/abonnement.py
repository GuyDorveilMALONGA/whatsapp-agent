"""
skills/abonnement.py
Crée un abonnement + confirme à l'usager.
"""
import re
from db import queries
from agent.extractor import extract, VALID_LINES


async def handle(message: str, contact: dict, langue: str) -> str:
    phone = contact["phone"]
    result = extract(message)

    if not result.ligne or not result.ligne_valide:
        ligne_str = result.ligne or "?"
        if langue == "wolof":
            return (f"Ligne {ligne_str} — duma ko xam ci réseau Dem Dikk yi. "
                    f"Wax ma numéro bus bi.")
        return (f"❌ La ligne *{ligne_str}* n'existe pas.\n"
                f"Lignes disponibles : {', '.join(sorted(VALID_LINES)[:10])}...")

    arret = result.arret_normalise or result.arret or ""

    # Extrait heure si mentionnée (ex: "07h30", "8h", "7:30")
    heure = _extract_heure(message)

    # Crée l'abonnement (idempotent)
    queries.create_abonnement(phone, result.ligne, arret, heure)

    # Réponse
    arret_str = f" près de *{arret}*" if arret else ""
    heure_str = f" à *{heure}*" if heure else ""

    if langue == "wolof":
        return (f"🔔 Waaw ! Bus {result.ligne}{arret_str} — maa ngiy gis. "
                f"Dinaa la wéer bu ñu ko signalé. 🙏")
    return (f"🔔 C'est noté ! Je t'alerterai dès que le Bus *{result.ligne}* "
            f"est signalé{arret_str}{heure_str}. 🙏")


def _extract_heure(text: str) -> str | None:
    """Extrait une heure depuis le texte (ex: '07h30', '8h', '07:30')."""
    match = re.search(r'\b(\d{1,2})[h:](\d{0,2})\b', text, re.IGNORECASE)
    if match:
        h = match.group(1).zfill(2)
        m = match.group(2).zfill(2) if match.group(2) else "00"
        return f"{h}:{m}"
    return None
