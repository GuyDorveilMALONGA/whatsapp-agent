"""
skills/signalement.py
Enregistre un signalement + notifie les abonnés.

FIX #1 : File d'envoi avec délai entre chaque message
→ évite le throttling/ban Meta si 100+ abonnés.
"""
import asyncio
import logging
from db import queries
from services.whatsapp import send_message
from agent.extractor import extract, VALID_LINES, NETWORK

logger = logging.getLogger(__name__)

# Délai entre chaque notification (évite ban Meta)
_NOTIFICATION_DELAY_SEC = 0.3
# Taille max de batch (sécurité supplémentaire)
_BATCH_SIZE = 50


def _ambigues_message(ambigues: list[str], langue: str) -> str:
    options = "\n".join([f"• *{l}* — {NETWORK[l].get('description', '')}" for l in ambigues])
    if langue == "wolof":
        return f"Bus bii — numéro yi ngi ci :\n{options}\nWax ma lignes bi ?"
    return f"Quel bus exactement ?\n{options}"


async def _notify_abonnes(ligne: str, arret: str, signaleur_phone: str):
    """
    Notifie les abonnés avec délai entre chaque envoi.
    Fire-and-forget — ne bloque pas la réponse au signaleur.
    """
    try:
        abonnes = queries.get_abonnes(ligne)
        alerte = (
            f"🔔 Bus {ligne} signalé à *{arret}* à l'instant.\n"
            f"Communauté Xëtu 🚌"
        )
        notifies = 0
        for i, abonne in enumerate(abonnes):
            if abonne["phone"] == signaleur_phone:
                continue
            if i > 0 and i % _BATCH_SIZE == 0:
                await asyncio.sleep(1.0)
            ok = await send_message(abonne["phone"], alerte)
            if ok:
                notifies += 1
            await asyncio.sleep(_NOTIFICATION_DELAY_SEC)

        logger.info(f"[Signalement] Bus {ligne} @ {arret} → {notifies} notifié(s)")
        return notifies
    except Exception as e:
        logger.error(f"[Signalement] Erreur notification: {e}")
        return 0


async def handle(message: str, contact: dict, langue: str) -> str:
    phone = contact["phone"]
    result = extract(message)

    if result.ambigues:
        return _ambigues_message(result.ambigues, langue)

    if not result.ligne or not result.ligne_valide:
        ligne_str = result.ligne or "inconnue"
        valides = ", ".join(sorted(VALID_LINES)[:10]) + "..."
        if langue == "wolof":
            return f"Bus bi {ligne_str} — duma ko xam ci réseau Dem Dikk yi. Lignes yi ngi ci : {valides}"
        return (f"❌ La ligne {ligne_str} n'existe pas dans le réseau Dem Dikk.\n"
                f"Lignes disponibles : {valides}")

    if not result.arret:
        if langue == "wolof":
            return f"Bus {result.ligne} — arrêt bi dafa soxor. Wax ma ci : 'Bus {result.ligne} à [arrêt bi]' 🙏"
        return (f"🚌 Bus {result.ligne} reçu ! Mais quel arrêt exactement ?\n"
                f"Envoie : *Bus {result.ligne} à [nom de l'arrêt]* 🙏")

    arret = result.arret_normalise or result.arret

    try:
        queries.save_signalement(result.ligne, arret, phone)
    except Exception as e:
        logger.error(f"Erreur save_signalement: {e}")
        return "❌ Erreur lors de l'enregistrement. Réessaie."

    try:
        abonnes = queries.get_abonnes(result.ligne)
        nb_abonnes = sum(1 for a in abonnes if a["phone"] != phone)
    except Exception:
        nb_abonnes = 0

    # Notifications en arrière-plan (fire-and-forget)
    asyncio.create_task(_notify_abonnes(result.ligne, arret, phone))

    if nb_abonnes == 0:
        if langue == "wolof":
            return f"✅ Jërëjëf ! Bus {result.ligne} ci {arret} — enregistré. 🙏"
        return f"✅ Merci ! Bus {result.ligne} à *{arret}* enregistré. 🙏"
    else:
        if langue == "wolof":
            return (f"✅ Jërëjëf ! Bus {result.ligne} ci {arret} — enregistré.\n"
                    f"Danga dém {nb_abonnes} nit 🙏")
        return (f"✅ Merci ! Bus {result.ligne} à *{arret}* enregistré.\n"
                f"Tu viens d'aider *{nb_abonnes}* personne(s) 🙏")
