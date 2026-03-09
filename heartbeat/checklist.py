"""
heartbeat/checklist.py — V2
Ce que fait le heartbeat toutes les 5 minutes :
1. Purge les signalements expirés
2. Détecte les lignes silencieuses (anomalies)
3. Envoie des alertes proactives aux abonnés

FIX V2 :
  - Source de vérité lignes → JSON (pas Supabase table lignes)
  - Déduplication alertes : 1 message max par (phone, ligne) par cycle
  - "Xëtu" corrigé (était "Sëtu")
"""
import json
import logging
from datetime import datetime, timezone

from db import queries
from services.whatsapp import send_message
from config.settings import ANOMALIE_SEUIL_MINUTES, ALERTE_PROACTIVE_AVANT

logger = logging.getLogger(__name__)

# ── Source de vérité : JSON (pas Supabase) ────────────────
_VALID_LINES: set = set()

try:
    with open("dem_dikk_lines_gps_final.json", "r", encoding="utf-8") as f:
        _RAW = json.load(f)
    for _lines in _RAW.get("categories", {}).values():
        for _line in _lines:
            num = str(_line.get("number", "")).upper()
            if num:
                _VALID_LINES.add(num)
    logger.info(f"[Heartbeat] {len(_VALID_LINES)} lignes chargées depuis JSON")
except Exception as e:
    logger.error(f"[Heartbeat] Erreur chargement JSON : {e}")


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
    """
    Détecte les lignes sans signalement depuis trop longtemps.
    Source : JSON uniquement — jamais la table Supabase `lignes`
    qui peut être désynchronisée.
    Actif uniquement aux heures de pointe.
    """
    try:
        heure = datetime.now(timezone.utc).hour
        heure_pointe = (7 <= heure <= 10) or (17 <= heure <= 20)
        if not heure_pointe:
            return

        if not _VALID_LINES:
            logger.warning("[Heartbeat] _VALID_LINES vide — JSON non chargé, anomalies ignorées")
            return

        silencieuses = queries.get_lignes_silencieuses(ANOMALIE_SEUIL_MINUTES)

        # Filtre : seulement les lignes qui existent dans le JSON
        silencieuses_valides = [l for l in silencieuses if str(l).upper() in _VALID_LINES]

        if silencieuses_valides:
            logger.warning(
                f"[Heartbeat] ⚠️ Lignes silencieuses depuis {ANOMALIE_SEUIL_MINUTES}min : "
                f"{', '.join(silencieuses_valides)}"
            )
    except Exception as e:
        logger.error(f"[Heartbeat] Erreur détection anomalies: {e}")


async def _alertes_proactives():
    """
    Envoie une alerte aux abonnés dont l'heure habituelle approche dans 15 min
    ET pour lesquels un signalement récent existe.

    Déduplication : 1 message max par (phone, ligne) par cycle heartbeat.
    """
    try:
        abonnes = queries.get_abonnements_proactifs(ALERTE_PROACTIVE_AVANT)

        # Déduplication : évite double-alerte si même usager abonné 2x même ligne
        deja_alerte: set = set()

        for abonne in abonnes:
            ligne = abonne.get("ligne")
            phone = abonne.get("phone")

            if not ligne or not phone:
                continue

            # Filtre : ligne doit exister dans le JSON
            if str(ligne).upper() not in _VALID_LINES:
                logger.debug(f"[Heartbeat] Ligne {ligne} inconnue dans JSON — abonnement ignoré")
                continue

            cle = (phone, str(ligne).upper())
            if cle in deja_alerte:
                logger.debug(f"[Heartbeat] Doublon ignoré : {phone[-4:]} / bus {ligne}")
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