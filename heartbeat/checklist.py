"""
heartbeat/checklist.py
Ce que fait le heartbeat toutes les 5 minutes :
1. Purge les signalements expirés
2. Détecte les lignes silencieuses (anomalies)
3. Envoie des alertes proactives aux abonnés
"""
import logging
from datetime import datetime, timezone

from db import queries
from services.whatsapp import send_message
from config.settings import ANOMALIE_SEUIL_MINUTES, ALERTE_PROACTIVE_AVANT

logger = logging.getLogger(__name__)


async def run_checklist():
    logger.info(f"[Heartbeat] {datetime.now(timezone.utc).strftime('%H:%M')} — démarrage")

    await _purge_signalements()
    await _detecter_anomalies()
    await _alertes_proactives()

    logger.info("[Heartbeat] ✅ terminé")


async def _purge_signalements():
    """Supprime les signalements expirés (> 20 min)."""
    try:
        queries.purge_signalements_expires()
        logger.debug("[Heartbeat] Purge signalements OK")
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur purge: {e}")


async def _detecter_anomalies():
    """Détecte les lignes sans signalement depuis trop longtemps."""
    try:
        # Seulement en heures de pointe (7h-10h, 17h-20h)
        heure = datetime.now(timezone.utc).hour + 0  # UTC → ajuster selon Dakar (UTC+0 en hiver)
        heure_pointe = (7 <= heure <= 10) or (17 <= heure <= 20)

        if not heure_pointe:
            return

        silencieuses = queries.get_lignes_silencieuses(ANOMALIE_SEUIL_MINUTES)
        if silencieuses:
            logger.warning(
                f"[Heartbeat] ⚠️ Lignes silencieuses depuis {ANOMALIE_SEUIL_MINUTES}min : "
                f"{', '.join(silencieuses)}"
            )
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur détection anomalies: {e}")


async def _alertes_proactives():
    """
    Envoie une alerte aux abonnés dont l'heure habituelle approche dans 15 min
    ET pour lesquels un signalement récent existe.
    """
    try:
        abonnes = queries.get_abonnements_proactifs(ALERTE_PROACTIVE_AVANT)

        for abonne in abonnes:
            ligne = abonne.get("ligne_id")
            if not ligne:
                continue

            signalements = queries.get_signalements_actifs(ligne)
            if not signalements:
                continue  # Pas de signalement → pas d'alerte

            s = signalements[0]
            msg = (
                f"🔔 Bus *{ligne}* signalé à *{s['arret_nom']}* "
                f"il y a quelques instants.\n"
                f"Ton bus approche ! Communauté Sëtu 🚌"
            )
            await send_message(abonne["phone"], msg)
            logger.info(f"[Heartbeat] Alerte proactive → {abonne['phone']} (bus {ligne})")

    except Exception as e:
        logger.error(f"[Heartbeat] Erreur alertes proactives: {e}")
