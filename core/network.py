"""
core/network.py — V6.0
Singleton JSON réseau Dem Dikk — source de vérité unique.

MIGRATION V6.0 depuis V5.3 :
  - Source : routes_geometry_v13_fixed2.json → xetu_network_v3.json
  - Format V3 : {"arrets": {"ligne_1": [...]}, "lignes": {"ligne_1": {...}}, "hubs": [...], "quartiers": [...]}
  - Clés V3 : "ligne_1" → NETWORK["1"], "ligne_16a" → NETWORK["16A"], "ligne_218a" → NETWORK["218A"]
  - Arrêts V3 : lat/lng (pas lat/lon), noms[] (multi-noms), nom_principal, pas de travel_time
  - _ARRETS_INDEX alimenté avec TOUS les noms[] de chaque arrêt (pas juste le premier)
  - HUBS et QUARTIERS exposés en tant que données globales
  - _build_graph_data() adapté : lng→lon, travel_time_to_next_sec=None (fallback 120s dans graph.py)
  - get_unified_index() simplifié : noms[] remplace les aliases_terrain
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
HUBS: list[dict] = []
QUARTIERS: list[dict] = []

# ── Logs de diagnostic Railway ────────────────────────────
logger.info(f"[Network] CWD       = {os.getcwd()}")
logger.info(f"[Network] JSON_PATH = {JSON_PATH}")
logger.info(f"[Network] Existe    = {os.path.exists(JSON_PATH)}")
try:
    logger.info(f"[Network] Contenu CWD = {os.listdir('.')[:15]}")
except Exception:
    pass

# ─────────────────────────────────────────────────────────────
# Chargement JSON — V6.0 format xetu_network_v3.json
# ─────────────────────────────────────────────────────────────

def _lid_to_num(lid: str) -> str:
    """ligne_1 → 1, ligne_16a → 16A, ligne_218a → 218A"""
    return lid.replace("ligne_", "").upper().strip()


def _adapt_stop_v3(stop: dict) -> dict:
    """Convertit un arrêt V3 au format attendu par le reste du code (lat/lon)."""
    return {
        "nom":  stop.get("nom_principal", stop.get("nom", "")),
        "lat":  stop.get("lat"),
        "lon":  stop.get("lng", stop.get("lon")),  # V3 = lng, legacy = lon
        "noms": stop.get("noms", []),
        "confiance_gps":  stop.get("confiance_gps", "haute"),
        "confiance_nom":  stop.get("confiance_nom", "haute"),
        "nom_quality":    stop.get("nom_quality", "lisible"),
        "id":             stop.get("id", ""),
        "ordre":          stop.get("ordre"),
    }


try:
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        _RAW = json.load(f)

    _arrets_raw = _RAW.get("arrets", {})
    _lignes_meta = _RAW.get("lignes", {})

    # Détection du format
    if _arrets_raw and isinstance(_arrets_raw, dict):
        # ── Format V3 : xetu_network_v3.json ──
        logger.info("[Network] Format V3 détecté (xetu_network_v3.json)")

        for lid, arrets_list in _arrets_raw.items():
            num = _lid_to_num(lid)
            if not num:
                continue

            meta = _lignes_meta.get(lid, {})
            adapted_stops = [_adapt_stop_v3(s) for s in arrets_list]

            NETWORK[num] = {
                "nom":        meta.get("nom_officiel", f"Ligne {num}"),
                "categorie":  meta.get("type", ""),
                "terminus_a": meta.get("terminus_depart", ""),
                "terminus_b": meta.get("terminus_arrivee", ""),
                "est_boucle": meta.get("est_boucle", False),
                "arrets":     adapted_stops,
            }

            # Indexer TOUS les noms de chaque arrêt
            for stop in arrets_list:
                for nom in stop.get("noms", []):
                    if nom and nom.lower() not in _ARRETS_INDEX:
                        _ARRETS_INDEX[nom.lower()] = nom
                # Aussi le nom_principal s'il n'est pas dans noms[]
                np = stop.get("nom_principal", "")
                if np and np.lower() not in _ARRETS_INDEX:
                    _ARRETS_INDEX[np.lower()] = np

        # Charger hubs et quartiers
        HUBS = _RAW.get("hubs", [])
        QUARTIERS = _RAW.get("quartiers", [])

    else:
        # ── Format legacy V13 : routes_geometry_v13_fixed2.json ──
        logger.info("[Network] Format legacy V13 détecté")
        _lignes_raw = _RAW.get("lignes") or _RAW.get("routes", {})

        for _line_id, _line in _lignes_raw.items():
            num = str(_line_id).upper().strip()
            if not num:
                continue
            NETWORK[num] = _line

            for stop in _line.get("arrets", _line.get("stops", [])):
                nom = stop.get("nom", stop.get("name", ""))
                if nom:
                    _ARRETS_INDEX[nom.lower()] = nom

            for _alias in _line.get("aliases_terrain", []):
                if _alias and _alias.lower() not in _ARRETS_INDEX:
                    _ARRETS_INDEX[_alias.lower()] = _alias

    logger.info(
        f"[Network] ✅ {len(NETWORK)} lignes · "
        f"{len(_ARRETS_INDEX)} arrêts+noms uniques · "
        f"{len(HUBS)} hubs · {len(QUARTIERS)} quartiers "
        f"({JSON_PATH})"
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
                "nom":                     s.get("nom", s.get("name", "")),
                "lat":                     s.get("lat"),
                "lon":                     s.get("lon"),
                "travel_time_to_next_sec": s.get("temps_vers_suivant_sec",
                                                  s.get("travel_time_to_next_sec")),
                "noms":                    s.get("noms", []),
            })

        # Collecter tous les noms alternatifs comme aliases_terrain
        aliases = []
        for s in raw_stops:
            for nom in s.get("noms", [])[1:]:  # skip le premier (= nom principal)
                if nom:
                    aliases.append(nom)

        lines_list.append({
            "number":          line_id,
            "name":            line.get("nom", line.get("name", "")),
            "category":        line.get("categorie", line.get("category", line.get("service", ""))),
            "terminus_a":      line.get("terminus_a", ""),
            "terminus_b":      line.get("terminus_b", ""),
            "stops":           stops_compat,
            "aliases_terrain": aliases,
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


def get_hubs() -> list[dict]:
    return HUBS


def get_quartiers() -> list[dict]:
    return QUARTIERS


def find_quartier(nom: str) -> dict | None:
    """Trouve un quartier par nom (fuzzy)."""
    nom_lower = nom.lower().strip()
    for q in QUARTIERS:
        if q["nom"].lower() == nom_lower:
            return q
    # Fuzzy
    for q in QUARTIERS:
        if nom_lower in q["nom"].lower() or q["nom"].lower() in nom_lower:
            return q
    return None


def get_unified_index() -> dict[str, dict]:
    """
    Index fusionné : tous les noms[] de chaque arrêt, lazy-loaded.
    En V3 les noms[] remplacent les aliases_terrain.
    """
    global _UNIFIED_INDEX
    if _UNIFIED_INDEX is not None:
        return _UNIFIED_INDEX

    index: dict[str, dict] = {}

    for line_id, line in NETWORK.items():
        raw_stops = line.get("arrets", line.get("stops", []))

        for stop in raw_stops:
            lat = stop.get("lat")
            lon = stop.get("lon")

            # Indexer le nom principal
            nom = stop.get("nom", stop.get("name", ""))
            if nom:
                key = _normalize_key(nom)
                if key not in index:
                    index[key] = {
                        "nom_officiel": nom,
                        "ligne":        line_id,
                        "lat":          lat,
                        "lon":          lon,
                        "source":       "officiel",
                    }

            # Indexer tous les noms alternatifs (V3 noms[])
            for alt_nom in stop.get("noms", [])[1:]:
                if not alt_nom:
                    continue
                key = _normalize_key(alt_nom)
                if key not in index:
                    index[key] = {
                        "nom_officiel": nom or alt_nom,
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