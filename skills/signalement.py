"""
skills/signalement.py
Enregistre un signalement + notifie les abonnés.
"""
import logging
from db import queries
from services.whatsapp import send_message
from agent.extractor import extract, VALID_LINES, NETWORK

logger = logging.getLogger(__name__)


def _ambigues_message(ambigues: list[str], langue: str) -> str:
    options = "\n".join([f"• *{l}* — {NETWORK[l].get('description', '')}" for l in ambigues])
    if langue == "wolof":
        return f"Bus bii — numéro yi ngi ci :\n{options}\nWax ma lignes bi ?"
    return f"Quel bus exactement ?\n{options}"


async def handle(message: str, contact: dict, langue: str) -> str:
    phone = contact["phone"]
    result = extract(message)

    # Ambiguïté (ex: 16A ou 16B)
    if result.ambigues:
        return _ambigues_message(result.ambigues, langue)

    # Ligne introuvable ou invalide
    if not result.ligne or not result.ligne_valide:
        ligne_str = result.ligne or "inconnue"
        valides = ", ".join(sorted(VALID_LINES)[:10]) + "..."
        if langue == "wolof":
            return f"Bus bi {ligne_str} — duma ko xam ci réseau Dem Dikk yi. Lignes yi ngi ci : {valides}"
        return (f"❌ La ligne {ligne_str} n'existe pas dans le réseau Dem Dikk.\n"
                f"Lignes disponibles : {valides}")

    # Arrêt manquant
    if not result.arret:
        if langue == "wolof":
            return f"Bus {result.ligne} — arrêt bi dafa soxor. Wax ma ci : 'Bus {result.ligne} à [arrêt bi]' 🙏"
        return (f"🚌 Bus {result.ligne} reçu ! Mais quel arrêt exactement ?\n"
                f"Envoie : *Bus {result.ligne} à [nom de l'arrêt]* 🙏")

    arret = result.arret_normalise or result.arret

    # Enregistre le signalement
    try:
        queries.save_signalement(result.ligne, arret, phone)
    except Exception as e:
        logger.error(f"Erreur save_signalement: {e}")
        return "❌ Erreur lors de l'enregistrement. Réessaie."

    # Notifie les abonnés
    abonnes = queries.get_abonnes(result.ligne)
    notifies = 0
    for abonne in abonnes:
        if abonne["phone"] == phone:
            continue
        alerte = (
            f"🔔 Bus {result.ligne} signalé à *{arret}* à l'instant.\n"
            f"Communauté Sëtu 🚌"
        )
        ok = await send_message(abonne["phone"], alerte)
        if ok:
            notifies += 1

    # Réponse au signaleur
    if notifies == 0:
        if langue == "wolof":
            return f"✅ Jërëjëf ! Bus {result.ligne} ci {arret} — enregistré. 🙏"
        return f"✅ Merci ! Bus {result.ligne} à *{arret}* enregistré. 🙏"
    else:
        if langue == "wolof":
            return (f"✅ Jërëjëf ! Bus {result.ligne} ci {arret} — enregistré.\n"
                    f"Danga dém {notifies} nit 🙏")
        return (f"✅ Merci ! Bus {result.ligne} à *{arret}* enregistré.\n"
                f"Tu viens d'aider *{notifies}* personne(s) 🙏")