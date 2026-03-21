"""
api/tracking.py — V1.0
POST /tracking/update — Signalement GPS automatique.

Utilisé par :
  - services/telegram.py  : messages location Telegram
  - (futur) PWA           : bouton "Je vois le bus" avec géolocalisation

LOGIQUE :
  1. Anti-spam : rejeter si même phone a signalé < 30s (toutes lignes confondues)
  2. Lookup session : si l'usager avait déjà dit "Bus X" → pré-filtrer sur cette ligne
  3. find_stops_nearby(lat, lon, radius_m=150) via DemDikkGraph
  4. Si ligne connue (session ou body) : filtrer sur cette ligne uniquement
  5. Si ligne absente : prendre l'arrêt le plus proche < 150m, toutes lignes
  6. Fallback radius 400m si rien < 150m
  7. save_signalement_gps() avec TTL 10min
  8. notify_abonnes() en background

TTL GPS = 10min (vs 20min pour signalements texte).
Ce TTL est local à ce module — ne pas modifier settings.py.
"""
import logging
from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, field_validator

from agent.graph import get_graph
from db.queries import is_recent_gps_signalement, save_signalement_gps
from core.session_manager import get_context
import skills.signalement as skill_signalement

logger = logging.getLogger(__name__)
router = APIRouter()

# TTL local GPS — intentionnellement séparé de SIGNALEMENT_TTL_MINUTES (20min)
_GPS_TTL_MINUTES   = 10
_GPS_ANTISPAM_SECS = 30
_RADIUS_PRIMARY_M  = 150
_RADIUS_FALLBACK_M = 400


# ── Schéma Pydantic ───────────────────────────────────────

class TrackingUpdate(BaseModel):
    phone: str
    lat:   float
    lon:   float
    ligne: str | None = None

    @field_validator("phone")
    @classmethod
    def phone_non_vide(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("phone ne peut pas être vide")
        return v.strip()

    @field_validator("lat")
    @classmethod
    def lat_plausible(cls, v: float) -> float:
        if not (-90 <= v <= 90):
            raise ValueError(f"lat hors bornes: {v}")
        return v

    @field_validator("lon")
    @classmethod
    def lon_plausible(cls, v: float) -> float:
        if not (-180 <= v <= 180):
            raise ValueError(f"lon hors bornes: {v}")
        return v


# ── Endpoint ─────────────────────────────────────────────

@router.post("/tracking/update")
async def tracking_update(body: TrackingUpdate, background_tasks: BackgroundTasks):
    """
    Reçoit une position GPS et enregistre le bus Dem Dikk le plus proche.

    Priorité pour la ligne :
      1. body.ligne (fourni explicitement par le client)
      2. session LangGraph de l'usager (ex: il venait de demander "Bus 15 est où ?")
      3. Aucune → on prend la 1ère ligne de l'arrêt le plus proche

    Retourne :
      {"status": "ok",           "ligne": "...", "arret": "..."}  ← succès
      {"status": "no_stop_found"}                                  ← aucun arrêt proche
      {"status": "spam"}                                           ← anti-spam déclenché
      {"status": "db_error"}                                       ← erreur Supabase
    """
    phone = body.phone
    lat   = body.lat
    lon   = body.lon

    # ── Résolution de la ligne ────────────────────────────
    # Priorité 1 : fournie dans le body
    ligne = body.ligne.upper().strip() if body.ligne else None

    # Priorité 2 : session LangGraph (ex: l'usager parlait du Bus 15)
    if not ligne:
        try:
            session = get_context(phone)
            if session.ligne:
                ligne = session.ligne.upper().strip()
                logger.info(
                    f"[tracking] Ligne inférée depuis session — "
                    f"{phone[-4:]} → {ligne}"
                )
        except Exception as e:
            # Session indisponible → on continue sans filtre ligne
            logger.warning(f"[tracking] Session lookup erreur: {e}")

    # ── Anti-spam ─────────────────────────────────────────
    try:
        if is_recent_gps_signalement(phone, window_seconds=_GPS_ANTISPAM_SECS):
            logger.info(f"[tracking] Anti-spam déclenché — {phone[-4:]}")
            return {"status": "spam"}
    except Exception as e:
        logger.error(f"[tracking] Anti-spam check erreur: {e}")
        # fail open — on continue

    # ── Recherche d'arrêts proches ────────────────────────
    graph = get_graph()
    arret_trouve, ligne_trouvee = _find_best_stop(graph, lat, lon, ligne)

    if not arret_trouve:
        logger.info(
            f"[tracking] Aucun arrêt Dem Dikk dans {_RADIUS_FALLBACK_M}m "
            f"— lat={lat:.5f} lon={lon:.5f} phone={phone[-4:]}"
        )
        return {"status": "no_stop_found"}

    # ── Enregistrement ────────────────────────────────────
    try:
        result = save_signalement_gps(
            ligne=ligne_trouvee,
            arret=arret_trouve,
            phone=phone,
            ttl_minutes=_GPS_TTL_MINUTES,
        )
        if result is None:
            # save_signalement_gps logge déjà l'erreur
            return {"status": "db_error"}
    except Exception as e:
        logger.error(f"[tracking] save_signalement_gps exception: {e}")
        return {"status": "db_error"}

    # ── Notification abonnés (background) ─────────────────
    background_tasks.add_task(
        skill_signalement.notify_abonnes,
        ligne_trouvee, arret_trouve, phone,
    )

    logger.info(
        f"[tracking] ✅ GPS — {phone[-4:]} → ligne={ligne_trouvee} "
        f"arret={arret_trouve!r}"
    )
    return {
        "status": "ok",
        "ligne":  ligne_trouvee,
        "arret":  arret_trouve,
    }


# ── Logique métier ────────────────────────────────────────

def _find_best_stop(
    graph,
    lat: float,
    lon: float,
    ligne_filter: str | None,
) -> tuple[str | None, str | None]:
    """
    Trouve l'arrêt Dem Dikk le plus proche compatible avec ligne_filter.

    Retourne (arret_display, ligne) ou (None, None).

    Stratégie :
      1. Chercher dans radius 150m
      2. Si rien → fallback 400m
      3. Si ligne_filter : garder seulement les arrêts de cette ligne
      4. Parmi les candidats : prendre le plus proche (find_stops_nearby trie déjà)
    """
    for radius in (_RADIUS_PRIMARY_M, _RADIUS_FALLBACK_M):
        nearby = graph.find_stops_nearby(lat, lon, radius_m=radius)
        if not nearby:
            continue

        if ligne_filter:
            # Garder uniquement les arrêts où cette ligne passe
            candidates = [
                s for s in nearby
                if ligne_filter in graph.stop_to_lines.get(s["canon"], [])
            ]
        else:
            candidates = nearby

        if not candidates:
            # Ligne filtrée mais aucun arrêt de cette ligne dans ce rayon
            # → on continue avec le rayon suivant (fallback 400m)
            continue

        # Le plus proche est en tête (find_stops_nearby trie par dist_m)
        best  = candidates[0]
        canon = best["canon"]

        if ligne_filter:
            return best["display"], ligne_filter

        # Pas de filtre ligne → prendre la 1ère ligne de l'arrêt le plus proche
        lines_at_stop = graph.stop_to_lines.get(canon, [])
        if not lines_at_stop:
            # Arrêt sans ligne dans le graphe — ne devrait pas arriver
            logger.warning(f"[tracking] Arrêt sans ligne dans graphe: {canon!r}")
            continue

        return best["display"], lines_at_stop[0]

    return None, None