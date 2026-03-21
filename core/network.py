"""
core/network.py — V5.2
Singleton JSON réseau Dem Dikk — source de vérité unique.

MIGRATIONS V5.2 depuis V5.1 :
  - Ajout get_unified_index() : index fusionné officiel + aliases terrain,
    lazy-loaded, mis en cache dans _UNIFIED_INDEX.
  - _ARRETS_INDEX étendu aux aliases_terrain au chargement.
  - Helpers privés : _normalize_key(), _find_best_official_stop().

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
  from core.network import get_unified_index
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

NETWORK: dict[str, dict] = {}     # "232" → {name, stops, geometry, ...}
# FIX BUG-M1 : source unique — VALID_LINES calculé dans config/settings.py
# On ré-exporte ici pour compatibilité des imports existants
from config.settings import VALID_LINES

_RAW: dict = {}
_ARRETS_INDEX: dict[str, str] = {}   # lower → nom (officiel ou alias terrain)
_GRAPH_DATA: dict | None = None       # format attendu par agent/graph._build()
_UNIFIED_INDEX: dict[str, dict] | None = None  # cache get_unified_index()

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

        # CHG-2 : aliases terrain inclus dans _ARRETS_INDEX
        for _alias in _line.get("aliases_terrain", []):
            if _alias and _alias.lower() not in _ARRETS_INDEX:
                _ARRETS_INDEX[_alias.lower()] = _alias

    logger.info(
        f"[Network] ✅ {len(VALID_LINES)} lignes · "
        f"{len(_ARRETS_INDEX)} arrêts+aliases uniques chargés ({JSON_PATH})"
    )

except FileNotFoundError:
    logger.error(f"[Network] ❌ Fichier introuvable : {JSON_PATH}")
except Exception as e:
    logger.error(f"[Network] ❌ Erreur critique chargement JSON : {e}")

print(f"[Network] FIN CHARGEMENT — NETWORK={len(NETWORK)} lignes", flush=True, file=sys.stderr)


# ─────────────────────────────────────────────────────────────
# Helpers privés pour get_unified_index()
# ─────────────────────────────────────────────────────────────

def _normalize_key(text: str) -> str:
    """lowercase + strip accents + tirets/apostrophes → espace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().replace("-", " ").replace("'", " ").replace("\u2019", " ").strip()


def _find_best_official_stop(alias: str, stops: list[dict]) -> dict | None:
    """
    Retourne l'arrêt officiel le plus proche textuellement (ratio >= 0.55).
    Cherche uniquement parmi les arrêts de la même ligne.
    """
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
    global _GRAPH_DATA
    lines_list = []
    for line_id, line in NETWORK.items():
        stops_compat = []
        # FIX BUG13 : JSON v13 → "arrets"+"nom"+"temps_vers_suivant_sec"
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
            "number":     line_id,
            "name":       line.get("nom",  line.get("name", "")),
            "category":   line.get("categorie", line.get("category", line.get("service", ""))),
            "terminus_a": line.get("terminus_a", ""),
            "terminus_b": line.get("terminus_b", ""),
            "stops":      stops_compat,
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
    """Retourne les arrêts d'une ligne. Insensible à la casse.
    FIX BUG13 : JSON v13 utilise 'arrets', pas 'stops'.
    """
    line = NETWORK.get(str(ligne).upper(), {})
    return line.get("arrets", line.get("stops", []))


def get_stop_names(ligne: str) -> list[str]:
    # FIX BUG13 : JSON v13 utilise "nom", pas "name"
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
    Mis en cache dans _UNIFIED_INDEX après le premier appel.

    Retourne un dict à clés normalisées (_normalize_key) :
    {
      "terminus ouakam": {
          "nom_officiel": "Terminus Ouakam",
          "ligne": "7",
          "lat": 14.7215,
          "lon": -17.506,
          "source": "officiel"   # ou "terrain"
      },
      "gare ouakam": {
          "nom_officiel": "Terminus Ouakam",   # résolu par SequenceMatcher
          "ligne": "7",
          "lat": 14.7215,
          "lon": -17.506,
          "source": "terrain"
      },
    }

    Collision inter-lignes sur arrêts officiels : premier chargé gagne
    (arrêt physique partagé → une entrée canonique suffit pour le routing).
    Aliases terrain sans match (ratio < 0.55) → lat/lon = None.
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
                    "ligne": line_id,
                    "lat": stop.get("lat"),
                    "lon": stop.get("lon"),
                    "source": "officiel",
                }

        # 2. Aliases terrain
        for alias in line.get("aliases_terrain", []):
            if not alias:
                continue
            key = _normalize_key(alias)
            if key in index:
                continue  # déjà présent (officiel ou alias antérieur)

            matched = _find_best_official_stop(alias, raw_stops)
            if matched:
                nom_officiel = matched.get("nom", matched.get("name", alias))
                lat = matched.get("lat")
                lon = matched.get("lon")
            else:
                nom_officiel = alias  # fallback : alias reste son propre nom
                lat = None
                lon = None

            index[key] = {
                "nom_officiel": nom_officiel,
                "ligne": line_id,
                "lat": lat,
                "lon": lon,
                "source": "terrain",
            }

    _UNIFIED_INDEX = index

    nb_officiel = sum(1 for v in _UNIFIED_INDEX.values() if v["source"] == "officiel")
    nb_terrain  = sum(1 for v in _UNIFIED_INDEX.values() if v["source"] == "terrain")
    nb_no_coords = sum(1 for v in _UNIFIED_INDEX.values() if v["lat"] is None)
    logger.info(
        f"[Network] _UNIFIED_INDEX construit — "
        f"{len(_UNIFIED_INDEX)} entrées "
        f"({nb_officiel} officiels, {nb_terrain} terrain, {nb_no_coords} sans coords)"
    )

    return _UNIFIED_INDEX