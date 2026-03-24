"""
core/network.py — V5.3
Singleton JSON réseau Dem Dikk — source de vérité unique.

MIGRATIONS V5.3 depuis V5.2 :
  - FIX CRITIQUE : lecture JSON corrigée pour format v13_fixed2
    Format réel : {"lignes": {"1": {...}, "4": {...}}} (dict keyed by numero)
    Avant : cherchait "routes" puis "lignes" mais itérait comme si c'était
    un format différent → NETWORK vide → 0 arrêts → aucun itinéraire trouvé
    Maintenant : itère correctement sur dict lignes, lit "arrets"+"nom"
  - _build_graph_data() : aliases_terrain lu depuis le bon endroit
  - Cache pickle invalidé automatiquement (hash JSON change)

MIGRATIONS V5.2 depuis V5.1 :
  - Ajout get_unified_index() : index fusionné officiel + aliases terrain
  - _ARRETS_INDEX étendu aux aliases_terrain au chargement

MIGRATIONS V5.1 depuis V5.0 :
  - Logs de diagnostic au démarrage pour Railway

MIGRATIONS V5.0 depuis V4 :
  - Source : routes_geometry_v4.json → routes_geometry_v13.json
  - Adaptateur _build_graph_data() pour agent/graph.py
"""

import sys
import os
print(f"[Network] DÉMARRAGE — PID={os.getpid()}", flush=True, file=sys.stderr)

import json
import logging
import unicodedata
from difflib import SequenceMatcher

from config.settings import JSON_PATH

logger = logging.getLogger(__name__)

NETWORK: dict[str, dict] = {}
from config.settings import VALID_LINES

_RAW: dict = {}
_ARRETS_INDEX: dict[str, str] = {}
_GRAPH_DATA: dict | None = None
_UNIFIED_INDEX: dict[str, dict] | None = None

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

    # Format v13_fixed2 : {"lignes": {"1": {...}, "4": {...}}}
    # Format legacy     : {"routes": {"1": {...}}}
    _lignes_raw = _RAW.get("lignes") or _RAW.get("routes", {})

    for _line_id, _line in _lignes_raw.items():
        num = str(_line_id).upper().strip()
        if not num:
            continue
        NETWORK[num] = _line

        # Arrêts officiels — JSON v13_fixed2 : "arrets" + "nom"
        for stop in _line.get("arrets", _line.get("stops", [])):
            nom = stop.get("nom", stop.get("name", ""))
            if nom:
                _ARRETS_INDEX[nom.lower()] = nom

        # Aliases terrain
        for _alias in _line.get("aliases_terrain", []):
            if _alias and _alias.lower() not in _ARRETS_INDEX:
                _ARRETS_INDEX[_alias.lower()] = _alias

    logger.info(
        f"[Network] ✅ {len(NETWORK)} lignes · "
        f"{len(_ARRETS_INDEX)} arrêts+aliases uniques chargés ({JSON_PATH})"
    )

except FileNotFoundError:
    logger.error(f"[Network] ❌ Fichier introuvable : {JSON_PATH}")
except Exception as e:
    logger.error(f"[Network] ❌ Erreur critique chargement JSON : {e}", exc_info=True)

print(f"[Network] FIN CHARGEMENT — NETWORK={len(NETWORK)} lignes", flush=True, file=sys.stderr)


# ─────────────────────────────────────────────────────────────
# Helpers privés
# ─────────────────────────────────────────────────────────────

def _normalize_key(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().replace("-", " ").replace("'", " ").replace("\u2019", " ").strip()


def _find_best_official_stop(alias: str, stops: list[dict]) -> dict | None:
    alias_norm = _normalize_key(alias)
    best_ratio = 0.0
    best_stop: dict | None = None
    for stop in stops:
        nom = stop.get("nom", stop.get("name", ""))
        if not nom:
            continue
        ratio = SequenceMatcher(None, alias_norm, _normalize_key(nom)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_stop = stop
    return best_stop if best_ratio >= 0.55 else None


# ─────────────────────────────────────────────────────────────
# Graph data (adaptateur pour agent/graph.py)
# ─────────────────────────────────────────────────────────────

def _build_graph_data() -> dict:
    lines_list = []
    for line_id, line in NETWORK.items():
        stops_compat = []
        raw_stops = line.get("arrets", line.get("stops", []))
        for s in raw_stops:
            stops_compat.append({
                "nom":                     s.get("nom",  s.get("name", "")),
                "lat":                     s.get("lat"),
                "lon":                     s.get("lon"),
                "travel_time_to_next_sec": s.get("temps_vers_suivant_sec",
                                                   s.get("travel_time_to_next_sec")),
            })
        lines_list.append({
            "number":          line_id,
            "name":            line.get("nom",       line.get("name", "")),
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


# ─────────────────────────────────────────────────────────────
# API publique
# ─────────────────────────────────────────────────────────────

def get_stops(ligne: str) -> list[dict]:
    line = NETWORK.get(str(ligne).upper(), {})
    return line.get("arrets", line.get("stops", []))


def get_stop_names(ligne: str) -> list[str]:
    return [
        s.get("nom", s.get("name", "")).lower()
        for s in get_stops(ligne)
        if s.get("nom") or s.get("name")
    ]


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


def get_unified_index() -> dict[str, dict]:
    """
    Index fusionné officiel + aliases terrain, lazy-loaded.
    """
    global _UNIFIED_INDEX
    if _UNIFIED_INDEX is not None:
        return _UNIFIED_INDEX

    index: dict[str, dict] = {}

    for line_id, line in NETWORK.items():
        raw_stops = line.get("arrets", line.get("stops", []))

        # 1. Arrêts officiels
        for stop in raw_stops:
            nom = stop.get("nom", stop.get("name", ""))
            if not nom:
                continue
            key = _normalize_key(nom)
            if key not in index:
                index[key] = {
                    "nom_officiel": nom,
                    "ligne":        line_id,
                    "lat":          stop.get("lat"),
                    "lon":          stop.get("lon"),
                    "source":       "officiel",
                }

        # 2. Aliases terrain
        for alias in line.get("aliases_terrain", []):
            if not alias:
                continue
            key = _normalize_key(alias)
            if key in index:
                continue

            matched = _find_best_official_stop(alias, raw_stops)
            if matched:
                nom_officiel = matched.get("nom", matched.get("name", alias))
                lat = matched.get("lat")
                lon = matched.get("lon")
            else:
                nom_officiel = alias
                lat = None
                lon = None

            index[key] = {
                "nom_officiel": nom_officiel,
                "ligne":        line_id,
                "lat":          lat,
                "lon":          lon,
                "source":       "terrain",
            }

    _UNIFIED_INDEX = index

    nb_officiel  = sum(1 for v in _UNIFIED_INDEX.values() if v["source"] == "officiel")
    nb_terrain   = sum(1 for v in _UNIFIED_INDEX.values() if v["source"] == "terrain")
    nb_no_coords = sum(1 for v in _UNIFIED_INDEX.values() if v["lat"] is None)
    logger.info(
        f"[Network] _UNIFIED_INDEX construit — "
        f"{len(_UNIFIED_INDEX)} entrées "
        f"({nb_officiel} officiels, {nb_terrain} terrain, {nb_no_coords} sans coords)"
    )

    return _UNIFIED_INDEX