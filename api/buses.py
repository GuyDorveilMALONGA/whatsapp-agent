"""
api/buses.py — V4.0
GET /api/buses — Position estimée des bus actifs.

Algorithme Dead Reckoning dakarois :
  1. Récupère les signalements actifs depuis Supabase
  2. Calcule la position estimée selon le temps écoulé
  3. Détecte si le bus est au terminus
  4. Attribue un score de confiance (vert/jaune/rouge)

MIGRATION V4.0 depuis V3 :
  - _load_network() supprimé — plus de lecture directe du JSON
  - _LINES_INDEX construit depuis core.network.NETWORK (singleton)
  - Plus de désynchronisation possible avec les autres modules
  - 77 lignes · 3129 arrêts disponibles sans I/O supplémentaire
  - Champ arrêt : "name" (inchangé depuis v3)
"""

import logging
from datetime import datetime, timezone
from fastapi import APIRouter

from db import queries
from core.network import NETWORK

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Index depuis le singleton ──────────────────────────────
# core.network est déjà chargé au démarrage — zéro I/O ici.
# numéro de ligne → liste d'arrêts [{name, lat, lon, ...}]

def _get_stops(ligne: str) -> list[dict]:
    from core.network import NETWORK
    return NETWORK.get(ligne, {}).get("stops", [])


# ── Constantes ─────────────────────────────────────────────

INTERVALLE_DEFAUT_MIN = 15
CONFIANCE_VERT_MIN    = 10
CONFIANCE_JAUNE_MAX   = 30


# ── Utilitaires ────────────────────────────────────────────

def _minutes_depuis(iso_str: str) -> float:
    try:
        dt    = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return 999


def _confiance(minutes: float) -> dict:
    if minutes < CONFIANCE_VERT_MIN:
        return {"niveau": "vert",  "emoji": "🟢", "label": "Récent"}
    elif minutes < CONFIANCE_JAUNE_MAX:
        return {"niveau": "jaune", "emoji": "🟡", "label": "Estimé"}
    else:
        return {"niveau": "rouge", "emoji": "🔴", "label": "Ancien"}


def _position_estimee(
    stops: list[dict],
    arret_signale: str,
    minutes_ecoulees: float,
    intervalle_min: float,
) -> dict:
    """
    Calcule la position estimée du bus à partir du dernier arrêt signalé.
    Champ arrêt : "name" (v4+).

    V4.0 : utilise travel_time_to_next_sec si disponible dans les stops v13
    pour une estimation plus précise que l'intervalle moyen fixe.
    """
    arret_lower = arret_signale.lower().strip()

    # Trouver l'index de l'arrêt signalé
    idx_depart = None
    for i, s in enumerate(stops):
        if s.get("name", "").lower().strip() == arret_lower:
            idx_depart = i
            break

    # Arrêt non trouvé → premier arrêt avec GPS
    if idx_depart is None:
        for s in stops:
            if s.get("lat"):
                return {
                    "nom":         s["name"],
                    "lat":         s["lat"],
                    "lon":         s["lon"],
                    "idx":         0,
                    "au_terminus": False,
                }
        return {"nom": arret_signale, "lat": None, "lon": None,
                "idx": 0, "au_terminus": False}

    # V4.0 : estimation par travel_time_to_next_sec (OSRM réel) si disponible
    # Sinon fallback sur intervalle_min / nb_stops
    secondes_ecoulees = minutes_ecoulees * 60
    idx_estime        = idx_depart

    if stops[idx_depart].get("travel_time_to_next_sec") is not None:
        # Parcours les temps réels OSRM
        temps_cumul = 0.0
        for i in range(idx_depart, len(stops) - 1):
            t = stops[i].get("travel_time_to_next_sec") or intervalle_min * 60
            temps_cumul += t
            if temps_cumul >= secondes_ecoulees:
                break
            idx_estime = i + 1
    else:
        # Fallback : nb arrêts parcourus selon intervalle moyen
        arrets_parcourus = int(minutes_ecoulees / max(intervalle_min, 1))
        idx_estime = min(idx_depart + arrets_parcourus, len(stops) - 1)

    idx_estime = min(idx_estime, len(stops) - 1)
    au_terminus = (idx_estime >= len(stops) - 1)

    # Cherche l'arrêt estimé avec GPS (reculer si null)
    for i in range(idx_estime, -1, -1):
        s = stops[i]
        if s.get("lat"):
            return {
                "nom":         s["name"],
                "lat":         s["lat"],
                "lon":         s["lon"],
                "idx":         i,
                "au_terminus": au_terminus,
            }

    return {"nom": arret_signale, "lat": None, "lon": None,
            "idx": idx_depart, "au_terminus": False}


# ── Endpoint ───────────────────────────────────────────────

@router.get("/api/buses")
async def get_buses():
    """
    Retourne la liste des bus actifs avec leur position estimée.
    """
    try:
        all_sigs = queries.get_all_signalements_actifs()
    except Exception as e:
        logger.error(f"[/api/buses] Erreur Supabase: {e}")
        return {"buses": [], "error": "db_error"}

    # Network memory pour les intervalles réels
    network_memory = {}
    try:
        nm = queries.get_network_memory()
        for entry in nm:
            network_memory[entry["ligne"]] = entry.get("intervalle_moyen", INTERVALLE_DEFAUT_MIN)
    except Exception:
        pass

    # Garder uniquement le signalement le plus récent par ligne
    seen_lignes: dict[str, dict] = {}
    for sig in all_sigs:
        ligne = sig.get("ligne")
        if not ligne:
            continue
        if ligne not in seen_lignes:
            seen_lignes[ligne] = sig
        else:
            t_existing = seen_lignes[ligne].get("timestamp") or seen_lignes[ligne].get("created_at", "")
            t_current  = sig.get("timestamp") or sig.get("created_at", "")
            if _minutes_depuis(t_current) < _minutes_depuis(t_existing):
                seen_lignes[ligne] = sig

    buses = []
    for ligne, sig in seen_lignes.items():
        stops = _get_stops(ligne)
        if not stops:
            logger.warning(f"[/api/buses] Ligne {ligne} absente du réseau v13")
            continue

        arret_signale   = sig.get("position", "")
        created_at      = sig.get("timestamp") or sig.get("created_at", "")
        minutes_ecoules = _minutes_depuis(created_at)
        intervalle      = network_memory.get(ligne, INTERVALLE_DEFAUT_MIN)

        pos  = _position_estimee(stops, arret_signale, minutes_ecoules, intervalle)
        conf = _confiance(minutes_ecoules)

        repart_dans = None
        if pos["au_terminus"]:
            repart_dans = max(0, int(intervalle - (minutes_ecoules % intervalle)))

        buses.append({
            "ligne":                      ligne,
            "arret_signale":              arret_signale,
            "arret_estime":               pos["nom"],
            "lat":                        pos["lat"],
            "lon":                        pos["lon"],
            "au_terminus":                pos["au_terminus"],
            "repart_dans_min":            repart_dans,
            "minutes_depuis_signalement": round(minutes_ecoules, 1),
            "confiance":                  conf,
            "signale_par":                sig.get("phone", "")[-4:],
        })

    logger.info(f"[/api/buses] {len(buses)} bus actifs retournés")
    return {
        "buses":     buses,
        "total":     len(buses),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }