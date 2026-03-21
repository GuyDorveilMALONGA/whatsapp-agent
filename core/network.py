"""
core/network.py — V5.1
Singleton JSON réseau Dem Dikk — source de vérité unique.

MIGRATIONS V5.1 depuis V5.0 :
  - Logs de diagnostic au démarrage (CWD, JSON_PATH, os.path.exists)
    pour détecter immédiatement les FileNotFoundError silencieux sur Railway.
  - JSON_PATH vient de config.settings qui utilise pathlib depuis V8.1
    → chemin absolu garanti, plus de dépendance au CWD.

MIGRATIONS V5.0 depuis V4 :
  - Source : routes_geometry_v4.json → routes_geometry_v13.json
  - JSON_PATH lu depuis config.settings (variable d'env NETWORK_JSON_PATH)
  - 77 lignes · 3129 arrêts · score moyen 89.5
  - Champ stops : "name" (inchangé depuis v4)
  - Nouvelle structure : _RAW["routes"][id] directement (plus de "categories")
  - _build_graph_data() : adaptateur pour agent/graph.py qui attend
    le format { categories: { all: [ {number, stops:[{nom}]} ] } }
    → exposé via get_graph_data() pour zéro modification dans graph.py

Usage :
  from core.network import NETWORK, VALID_LINES, get_stops, get_line_info
"""

import sys, os
print(f"[Network] DÉMARRAGE — PID={os.getpid()}", flush=True, file=sys.stderr)

import json
import logging
import os
from config.settings import JSON_PATH

logger = logging.getLogger(__name__)

NETWORK: dict[str, dict] = {}     # "232" → {name, stops, geometry, ...}
# FIX BUG-M1 : source unique — VALID_LINES calculé dans config/settings.py
# On ré-exporte ici pour compatibilité des imports existants
from config.settings import VALID_LINES

_RAW: dict = {}
_ARRETS_INDEX: dict[str, str] = {}   # lower → officiel
_GRAPH_DATA: dict | None = None       # format attendu par agent/graph._build()

# ── Logs de diagnostic Railway ────────────────────────────
logger.info(f"[Network] CWD       = {os.getcwd()}")
logger.info(f"[Network] JSON_PATH = {JSON_PATH}")
logger.info(f"[Network] Existe    = {os.path.exists(JSON_PATH)}")
try:
    logger.info(f"[Network] Contenu CWD = {os.listdir('.')[:15]}")
except Exception:
    pass

try:
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        _RAW = json.load(f)

    for _line_id, _line in (_RAW.get("routes") or _RAW.get("lignes", {})).items():
        num = str(_line_id).upper()
        if not num:
            continue
        NETWORK[num] = _line
        # VALID_LINES géré par config/settings.py — pas besoin d'ajouter ici
        # FIX BUG13 : le JSON v13 utilise "arrets"+"nom", pas "stops"+"name"
        for stop in _line.get("arrets", _line.get("stops", [])):
            nom = stop.get("nom", stop.get("name", ""))
            if nom:
                _ARRETS_INDEX[nom.lower()] = nom

    logger.info(
        f"[Network] ✅ {len(VALID_LINES)} lignes · "
        f"{len(_ARRETS_INDEX)} arrêts uniques chargés ({JSON_PATH})"
    )

except FileNotFoundError:
    logger.error(f"[Network] ❌ Fichier introuvable : {JSON_PATH}")
except Exception as e:
    logger.error(f"[Network] ❌ Erreur critique chargement JSON : {e}")

print(f"[Network] FIN CHARGEMENT — NETWORK={len(NETWORK)} lignes", flush=True, file=sys.stderr)



def _build_graph_data() -> dict:
    global _GRAPH_DATA
    lines_list = []
    for line_id, line in NETWORK.items():
        stops_compat = []
        # FIX BUG13 : JSON v13 → "arrets"+"nom"+"temps_vers_suivant_sec"
        raw_stops = line.get("arrets", line.get("stops", []))
        for s in raw_stops:
            stops_compat.append({
                "nom":                    s.get("nom",  s.get("name", "")),
                "lat":                    s.get("lat"),
                "lon":                    s.get("lon"),
                "travel_time_to_next_sec": s.get("temps_vers_suivant_sec",
                                                   s.get("travel_time_to_next_sec")),
            })
        lines_list.append({
            "number":          line_id,
            "name":            line.get("nom",  line.get("name", "")),
            "category":        line.get("categorie", line.get("category", line.get("service", ""))),
            "terminus_a":      line.get("terminus_a", ""),
            "terminus_b":      line.get("terminus_b", ""),
            "stops":           stops_compat,
            "aliases_terrain": line.get("aliases_terrain", []),
        })
    return {"categories": {"all": lines_list}}


def get_graph_data() -> dict:
    global _GRAPH_DATA
    if _GRAPH_DATA is None:
        _GRAPH_DATA = _build_graph_data()
    return _GRAPH_DATA


def get_stops(ligne: str) -> list[dict]:
    """Retourne les arrêts d'une ligne. Insensible à la casse.
    FIX BUG13 : JSON v13 utilise 'arrets', pas 'stops'.
    """
    line = NETWORK.get(str(ligne).upper(), {})
    return line.get("arrets", line.get("stops", []))


def get_stop_names(ligne: str) -> list[str]:
    # FIX BUG13 : JSON v13 utilise "nom", pas "name"
    return [s.get("nom", s.get("name", "")).lower() for s in get_stops(ligne) if s.get("nom") or s.get("name")]


def get_line_info(ligne: str) -> dict:
    return NETWORK.get(str(ligne).upper(), {})


def all_stop_names() -> dict[str, str]:
    return _ARRETS_INDEX


def is_valid_line(ligne: str) -> bool:
    return str(ligne).upper() in VALID_LINES


def ambiguous_lines(prefix: str) -> list[str]:
    prefix = str(prefix).upper()
    matches = [l for l in VALID_LINES if l != prefix and l.startswith(prefix)]
    if matches and prefix not in VALID_LINES:
        return sorted(matches)
    return []