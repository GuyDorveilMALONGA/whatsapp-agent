"""
api/buses.py
GET /api/buses — Position estimée des bus actifs.

Algorithme Dead Reckoning dakarois :
  1. Récupère les signalements actifs depuis Supabase
  2. Calcule la position estimée selon le temps écoulé
  3. Détecte si le bus est au terminus
  4. Attribue un score de confiance (vert/jaune/rouge)
"""

import json
import math
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter

from db import queries

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Chargement réseau GPS ──────────────────────────────────

_NETWORK_FILE = Path(__file__).parent.parent / "dem_dikk_lines_gps_final.json"

def _load_network() -> dict:
    with open(_NETWORK_FILE, encoding="utf-8") as f:
        return json.load(f)

_NETWORK = _load_network()

# Index : numéro de ligne → liste d'arrêts [{nom, lat, lon}]
_LINES_INDEX: dict[str, list[dict]] = {}
for _cat in _NETWORK["categories"].values():
    for _ligne in _cat:
        _LINES_INDEX[_ligne["number"]] = _ligne["stops"]


# ── Constantes ─────────────────────────────────────────────

INTERVALLE_DEFAUT_MIN = 15   # Si pas de donnée network_memory
CONFIANCE_VERT_MIN    = 10   # minutes
CONFIANCE_JAUNE_MAX   = 30   # minutes


# ── Utilitaires ────────────────────────────────────────────

def _minutes_depuis(iso_str: str) -> float:
    """Retourne le nombre de minutes écoulées depuis une date ISO."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        return delta.total_seconds() / 60
    except Exception:
        return 999


def _confiance(minutes: float) -> dict:
    """Retourne le niveau de confiance selon le temps écoulé."""
    if minutes < CONFIANCE_VERT_MIN:
        return {"niveau": "vert", "emoji": "🟢", "label": "Récent"}
    elif minutes < CONFIANCE_JAUNE_MAX:
        return {"niveau": "jaune", "emoji": "🟡", "label": "Estimé"}
    else:
        return {"niveau": "rouge", "emoji": "🔴", "label": "Ancien"}


def _position_estimee(
    stops: list[dict],
    arret_signale: str,
    minutes_ecoulees: float,
    intervalle_min: float
) -> dict:
    """
    Calcule la position estimée du bus à partir du dernier arrêt signalé.
    Retourne l'arrêt estimé avec ses coordonnées GPS.
    """
    # Trouver l'index de l'arrêt signalé
    idx_depart = None
    for i, s in enumerate(stops):
        if s["nom"].lower() == arret_signale.lower():
            idx_depart = i
            break

    # Arrêt non trouvé → retourner le premier arrêt avec GPS
    if idx_depart is None:
        for s in stops:
            if s.get("lat"):
                return {
                    "nom": s["nom"],
                    "lat": s["lat"],
                    "lon": s["lon"],
                    "idx": 0,
                    "au_terminus": False,
                }
        return {"nom": arret_signale, "lat": None, "lon": None,
                "idx": 0, "au_terminus": False}

    # Calcul arrêts parcourus depuis le signalement
    arrets_parcourus = int(minutes_ecoulees / max(intervalle_min, 1))
    idx_estime = min(idx_depart + arrets_parcourus, len(stops) - 1)
    au_terminus = (idx_estime >= len(stops) - 1)

    # Cherche l'arrêt estimé avec GPS (reculer si null)
    for i in range(idx_estime, -1, -1):
        s = stops[i]
        if s.get("lat"):
            return {
                "nom": s["nom"],
                "lat": s["lat"],
                "lon": s["lon"],
                "idx": i,
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
        # Récupère tous les signalements actifs (toutes lignes)
        all_sigs = queries.get_all_signalements_actifs()
    except Exception as e:
        logger.error(f"[/api/buses] Erreur Supabase: {e}")
        return {"buses": [], "error": "db_error"}

    # Network memory pour les intervalles (si dispo)
    network_memory = {}
    try:
        nm = queries.get_network_memory()
        for entry in nm:
            network_memory[entry["ligne"]] = entry.get("intervalle_moyen", INTERVALLE_DEFAUT_MIN)
    except Exception:
        pass

    buses = []
    # On garde le signalement le plus récent par ligne
    seen_lignes: dict[str, dict] = {}
    for sig in all_sigs:
        ligne = sig.get("ligne_id") or sig.get("ligne")
        if not ligne:
            continue
        if ligne not in seen_lignes:
            seen_lignes[ligne] = sig
        else:
            # Garder le plus récent
            existing_min = _minutes_depuis(seen_lignes[ligne].get("created_at", ""))
            current_min  = _minutes_depuis(sig.get("created_at", ""))
            if current_min < existing_min:
                seen_lignes[ligne] = sig

    for ligne, sig in seen_lignes.items():
        stops = _LINES_INDEX.get(ligne)
        if not stops:
            continue

        arret_signale    = sig.get("arret_nom") or sig.get("position", "")
        created_at       = sig.get("created_at", "")
        minutes_ecoules  = _minutes_depuis(created_at)
        intervalle       = network_memory.get(ligne, INTERVALLE_DEFAUT_MIN)

        pos = _position_estimee(stops, arret_signale, minutes_ecoules, intervalle)
        conf = _confiance(minutes_ecoules)

        # Temps avant redépart si au terminus
        repart_dans = None
        if pos["au_terminus"]:
            repart_dans = max(0, int(intervalle - (minutes_ecoules % intervalle)))

        buses.append({
            "ligne":                    ligne,
            "arret_signale":            arret_signale,
            "arret_estime":             pos["nom"],
            "lat":                      pos["lat"],
            "lon":                      pos["lon"],
            "au_terminus":              pos["au_terminus"],
            "repart_dans_min":          repart_dans,
            "minutes_depuis_signalement": round(minutes_ecoules, 1),
            "confiance":                conf,
            "signale_par":              sig.get("phone", "")[-4:],  # 4 derniers chiffres
        })

    return {
        "buses":     buses,
        "total":     len(buses),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
