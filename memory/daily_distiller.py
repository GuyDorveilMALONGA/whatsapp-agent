"""
memory/daily_distiller.py — V2
Job nocturne lancé à 2h00 par APScheduler.
Agrège tous les signalements de la journée →
met à jour network_memory avec les patterns de ponctualité.
"""
import logging
from datetime import datetime, timezone, timedelta

from db.client import get_client
from memory.network_memory import upsert_memory_entry

logger = logging.getLogger(__name__)


async def run_distillation():
    """
    Point d'entrée du job nocturne.
    Récupère les signalements des dernières 24h et les distille.
    """
    logger.info("[Distiller] ▶ Démarrage distillation nocturne")

    try:
        signalements = _get_signalements_journee()
        if not signalements:
            logger.info("[Distiller] Aucun signalement à distiller")
            return

        # Groupe par ligne
        par_ligne: dict[str, list] = {}
        for s in signalements:
            ligne = s["ligne_id"]
            par_ligne.setdefault(ligne, []).append(s)

        total_entrees = 0
        for ligne, sigs in par_ligne.items():
            entrees = _distill_ligne(ligne, sigs)
            total_entrees += entrees

        logger.info(f"[Distiller] ✅ {total_entrees} entrées mises à jour pour {len(par_ligne)} lignes")

    except Exception as e:
        logger.error(f"[Distiller] Erreur: {e}", exc_info=True)


def _get_signalements_journee() -> list[dict]:
    """Récupère tous les signalements des dernières 24h (non purgés)."""
    db = get_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Note : on utilise une table d'archive ou les signalements non expirés
    # En production, créer une table signalements_archive pour garder l'historique
    res = (db.table("signalements")
             .select("ligne_id, arret_nom, created_at")
             .gt("created_at", since)
             .order("created_at")
             .execute())
    return res.data or []


def _distill_ligne(ligne: str, signalements: list[dict]) -> int:
    """
    Pour une ligne, calcule les intervalles entre signalements consécutifs
    et met à jour network_memory.
    Retourne le nombre d'entrées créées/mises à jour.
    """
    if len(signalements) < 2:
        return 0

    entrees = 0
    for i in range(1, len(signalements)):
        try:
            s_prev = signalements[i - 1]
            s_curr = signalements[i]

            t_prev = datetime.fromisoformat(s_prev["created_at"].replace("Z", "+00:00"))
            t_curr = datetime.fromisoformat(s_curr["created_at"].replace("Z", "+00:00"))

            intervalle_min = (t_curr - t_prev).total_seconds() / 60

            # Ignore les intervalles aberrants (> 2h ou < 30 sec)
            if intervalle_min < 0.5 or intervalle_min > 120:
                continue

            heure = t_curr.strftime("%H")
            jour = t_curr.weekday()

            # Segment = "arrêt_prev → arrêt_curr"
            segment = f"{s_prev['arret_nom']} → {s_curr['arret_nom']}"

            # Ponctuel si intervalle < 20 min (dans les TTL normaux)
            ponctuel = intervalle_min <= 20

            upsert_memory_entry(
                ligne_id=ligne,
                segment=segment,
                heure=heure,
                jour_semaine=jour,
                intervalle_min=intervalle_min,
                ponctuel=ponctuel,
            )
            entrees += 1

        except Exception as e:
            logger.warning(f"[Distiller] Erreur sur signalement {i}: {e}")

    return entrees
