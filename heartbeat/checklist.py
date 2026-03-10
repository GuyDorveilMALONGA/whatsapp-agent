"""
heartbeat/checklist.py — V3.0

MIGRATIONS V3.0 depuis V2 :
  - FIX B10 : VALID_LINES importé depuis config.settings (source unique)
    Plus de chargement JSON séparé — le JSON est chargé une seule fois
    par core.network au démarrage.
  - FIX H2 : Matching heure avec fenêtre de ±5 min au lieu d'exact
  - Ajout purge_sessions_expires dans le cycle
"""
import logging
from datetime import datetime, timezone, timedelta

from db import queries
from services.whatsapp import send_message
from config.settings import (
    VALID_LINES,
    ANOMALIE_SEUIL_MINUTES,
    ALERTE_PROACTIVE_AVANT,
)

logger = logging.getLogger(__name__)


async def run_checklist():
    logger.info(f"[Heartbeat] {datetime.now(timezone.utc).strftime('%H:%M')} — démarrage")

    await _purge_signalements()
    await _purge_sessions()
    await _detecter_anomalies()
    await _alertes_proactives()

    logger.info("[Heartbeat] ✅ terminé")


async def _purge_signalements():
    try:
        queries.purge_signalements_expires()
        logger.debug("[Heartbeat] Purge signalements OK")
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur purge signalements: {e}")


async def _purge_sessions():
    """Purge les sessions expirées en DB."""
    try:
        queries.purge_sessions_expires()
        logger.debug("[Heartbeat] Purge sessions OK")
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur purge sessions: {e}")


async def _detecter_anomalies():
    try:
        heure = datetime.now(timezone.utc).hour
        heure_pointe = (7 <= heure <= 10) or (17 <= heure <= 20)
        if not heure_pointe:
            return

        if not VALID_LINES:
            logger.warning("[Heartbeat] VALID_LINES vide — anomalies ignorées")
            return

        silencieuses = queries.get_lignes_silencieuses(ANOMALIE_SEUIL_MINUTES)
        silencieuses_valides = [l for l in silencieuses if str(l).upper() in VALID_LINES]

        if silencieuses_valides:
            logger.warning(
                f"[Heartbeat] ⚠️ Lignes silencieuses depuis {ANOMALIE_SEUIL_MINUTES}min : "
                f"{', '.join(silencieuses_valides)}"
            )
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur détection anomalies: {e}")


async def _alertes_proactives():
    """
    FIX H2 : Fenêtre de ±5 min au lieu de matching exact.
    Si le heartbeat tourne à 07:03 et l'usager a mis 07:05 → ça matche.
    """
    try:
        now = datetime.now(timezone.utc)

        # Générer toutes les minutes dans la fenêtre [now, now+avant+5min]
        heures_cibles = set()
        for delta_min in range(ALERTE_PROACTIVE_AVANT - 2, ALERTE_PROACTIVE_AVANT + 3):
            t = now + timedelta(minutes=delta_min)
            heures_cibles.add(t.strftime("%H:%M"))

        deja_alerte: set = set()

        for heure_cible in heures_cibles:
            abonnes = queries.get_abonnements_proactifs_heure(heure_cible)

            for abonne in abonnes:
                ligne = abonne.get("ligne")
                phone = abonne.get("phone")

                if not ligne or not phone:
                    continue

                if str(ligne).upper() not in VALID_LINES:
                    continue

                cle = (phone, str(ligne).upper())
                if cle in deja_alerte:
                    continue

                signalements = queries.get_signalements_actifs(ligne)
                if not signalements:
                    continue

                s = signalements[0]
                msg = (
                    f"🔔 Bus *{ligne}* signalé à *{s['position']}* "
                    f"il y a quelques instants.\n"
                    f"Ton bus approche ! — *Xëtu* 🚌"
                )
                await send_message(phone, msg)
                deja_alerte.add(cle)
                logger.info(f"[Heartbeat] Alerte proactive → {phone[-4:]} (bus {ligne})")

    except Exception as e:
        logger.error(f"[Heartbeat] Erreur alertes proactives: {e}")