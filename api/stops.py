"""
api/stops.py — V1.0
GET /api/stops/search?q=...&lat=...&lon=...

Recherche d'arrêts enrichie :
  - Fuzzy match sur NETWORK (routes_geometry_v13.json, chargé en mémoire)
  - Groupement par nom d'arrêt physique (multi-lignes)
  - Signalements actifs injectés par arrêt (TTL via expires_at, pas de re-query)
  - Tri par distance GPS si lat/lon fournis, sinon alphabétique
  - Max 10 résultats

Réponse :
{
  "stops": [
    {
      "nom": "Gare Aéroport Yoff",
      "lat": 14.7388,
      "lon": -17.4902,
      "distance_m": 1200,
      "lignes": [
        { "numero": "8",   "has_recent": true,  "last_seen_min": 6 },
        { "numero": "232", "has_recent": false,  "last_seen_min": null },
        { "numero": "305", "has_recent": false,  "last_seen_min": null }
      ]
    }
  ],
  "total": 4,
  "query": "yoff"
}
"""

import logging
import math
from datetime import datetime, timezone
from fastapi import APIRouter, Query

from core.network import NETWORK
from db.queries import get_all_signalements_actifs

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + \
        math.cos(lat1 * p) * math.cos(lat2 * p) * \
        math.sin((lon2 - lon1) * p / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _minutes_since(iso_str: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 60
    except Exception:
        return 999.0


def _normalize(s: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_s = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_s.lower().replace("-", " ").replace("'", " ").strip()


# ── Endpoint ──────────────────────────────────────────────

@router.get("/api/stops/search")
async def search_stops(
    q: str = Query(..., min_length=2, max_length=60),
    lat: float | None = Query(None),
    lon: float | None = Query(None),
):
    q_norm = _normalize(q)

    # 1. Récupérer tous les signalements actifs en 1 seul appel DB
    #    Structure : { (ligne, arret_lower) → last_seen_min }
    active_sigs: dict[tuple[str, str], float] = {}
    try:
        sigs = get_all_signalements_actifs()
        for s in sigs:
            ligne = str(s.get("ligne", "")).upper()
            arret = _normalize(s.get("position", ""))
            mins = _minutes_since(s.get("timestamp") or s.get("created_at", ""))
            key = (ligne, arret)
            if key not in active_sigs or mins < active_sigs[key]:
                active_sigs[key] = mins
    except Exception as e:
        logger.warning(f"[stops/search] Impossible de charger signalements: {e}")

    # 2. Grouper tous les arrêts du réseau par nom physique
    #    stops_map : nom_arret → { lignes: set, lat, lon }
    stops_map: dict[str, dict] = {}
    for ligne_id, ligne_data in NETWORK.items():
        for stop in ligne_data.get("arrets", ligne_data.get("stops", [])):
            nom = (stop.get("nom") or stop.get("name") or "").strip()
            if not nom:
                continue
            if _normalize(nom).find(q_norm) < 0:
                continue  # filtre fuzzy
            if nom not in stops_map:
                stops_map[nom] = {
                    "lat": stop.get("lat"),
                    "lon": stop.get("lon"),
                    "lignes": set(),
                }
            stops_map[nom]["lignes"].add(ligne_id.upper())

    # 3. Construire la réponse enrichie
    results = []
    for nom, info in stops_map.items():
        dist = None
        if lat is not None and lon is not None and info["lat"] and info["lon"]:
            dist = round(_haversine(lat, lon, info["lat"], info["lon"]))

        lignes_enrichies = []
        for num in sorted(info["lignes"], key=lambda x: (not x.isdigit(), x)):
            key = (num, _normalize(nom))
            last_seen = active_sigs.get(key)
            lignes_enrichies.append({
                "numero": num,
                "has_recent": last_seen is not None,
                "last_seen_min": round(last_seen) if last_seen is not None else None,
            })

        results.append({
            "nom": nom,
            "lat": info["lat"],
            "lon": info["lon"],
            "distance_m": dist,
            "lignes": lignes_enrichies,
        })

    # 4. Tri : distance GPS d'abord, puis signalés, puis alphabétique
    def _sort_key(r):
        has_sig = any(l["has_recent"] for l in r["lignes"])
        d = r["distance_m"] if r["distance_m"] is not None else 999999
        return (not has_sig, d, r["nom"])

    results.sort(key=_sort_key)
    results = results[:10]

    return {"stops": results, "total": len(results), "query": q}
