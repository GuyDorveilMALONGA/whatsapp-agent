"""
skills/signalement.py — V4 LLM-Driven
Enregistre un signalement + notifie les abonnés.

V4 : entities injectées depuis route_result (main.py)
     Suppression de l'import extractor
     _VALID_LINES et _NETWORK déclarés ici (découplé de l'extracteur)
     Cas ambiguïté conservé (deux lignes avec même numéro)

FIX #1 : File d'envoi avec délai entre chaque message
→ évite le throttling/ban Meta si 100+ abonnés.
"""
import asyncio
import logging
from db import queries
from services.whatsapp import send_message

logger = logging.getLogger(__name__)

# Délai entre chaque notification (évite ban Meta)
_NOTIFICATION_DELAY_SEC = 0.3
# Taille max de batch (sécurité supplémentaire)
_BATCH_SIZE = 50

# Référentiel des lignes valides (découplé de l'extracteur)
_VALID_LINES = {
    "1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "15",
    "16A", "16B", "18", "20", "23", "121", "208", "213", "217", "218", "219",
    "220", "221", "227", "232", "233", "234", "311", "319", "327",
    "TO1", "501", "502", "503", "TAF TAF", "RUF-YENNE"
}


async def _notify_abonnes(ligne: str, arret: str, signaleur_phone: str):
    """
    Notifie les abonnés avec délai entre chaque envoi.
    Fire-and-forget — ne bloque pas la réponse au signaleur.

    ⚠️ asyncio.create_task() : si Railway redémarre, tâches non terminées
    sont perdues. Migrer vers BackgroundTasks FastAPI ou Redis à l'échelle.
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


async def handle(message: str, contact: dict, langue: str, entities: dict) -> str:
    """
    Gère un signalement en utilisant les entités pré-extraites par le LLM.
    """
    phone = contact["phone"]

    # ── 1. Extraction depuis les entités LLM ──────────────
    ligne = entities.get("ligne")
    # L'arrêt peut être dans origin (tournure "Bus 15 à Liberté 5")
    # ou destination selon la formulation
    arret = entities.get("origin") or entities.get("destination")

    # ── 2. Validation de la ligne ─────────────────────────
    if not ligne:
        if langue == "wolof":
            return "Wax ma numéro bi — 'Bus 15 à Liberté 5' 🙏"
        return "❓ Quel numéro de bus ? Envoie : *Bus 15 à Liberté 5* 🙏"

    ligne_upper = str(ligne).upper()

    if ligne_upper not in _VALID_LINES:
        valides = ", ".join(sorted(_VALID_LINES)[:10]) + "..."
        if langue == "wolof":
            return (
                f"Bus bi {ligne} — duma ko xam ci réseau Dem Dikk yi.\n"
                f"Lignes yi ngi ci : {valides}"
            )
        return (
            f"❌ La ligne {ligne} n'existe pas dans le réseau Dem Dikk.\n"
            f"Lignes disponibles : {valides}"
        )

    ligne = ligne_upper

    # ── 3. Validation de l'arrêt ──────────────────────────
    if not arret:
        if langue == "wolof":
            return (
                f"Bus {ligne} — arrêt bi dafa soxor.\n"
                f"Wax ma ci : 'Bus {ligne} à [arrêt bi]' 🙏"
            )
        return (
            f"🚌 Bus {ligne} reçu ! Mais quel arrêt exactement ?\n"
            f"Envoie : *Bus {ligne} à [nom de l'arrêt]* 🙏"
        )

    # ── 4. Enregistrement en base ─────────────────────────
    try:
        queries.save_signalement(ligne, arret, phone)
    except Exception as e:
        logger.error(f"Erreur save_signalement: {e}")
        return "❌ Erreur lors de l'enregistrement. Réessaie."

    # ── 5. Comptage abonnés ───────────────────────────────
    try:
        abonnes = queries.get_abonnes(ligne)
        nb_abonnes = sum(1 for a in abonnes if a["phone"] != phone)
    except Exception:
        nb_abonnes = 0

    # ── 6. Notifications en arrière-plan ──────────────────
    asyncio.create_task(_notify_abonnes(ligne, arret, phone))

    # ── 7. Réponse ────────────────────────────────────────
    if nb_abonnes == 0:
        if langue == "wolof":
            return f"✅ Jërëjëf ! Bus {ligne} ci {arret} — enregistré. 🙏"
        return f"✅ Merci ! Bus {ligne} à *{arret}* enregistré. 🙏"
    else:
        if langue == "wolof":
            return (
                f"✅ Jërëjëf ! Bus {ligne} ci {arret} — enregistré.\n"
                f"Danga dém {nb_abonnes} nit 🙏"
            )
        return (
            f"✅ Merci ! Bus {ligne} à *{arret}* enregistré.\n"
            f"Tu viens d'aider *{nb_abonnes}* personne(s) 🙏"
        )