"""
core/network.py — Singleton JSON réseau Dem Dikk
Source de vérité unique pour TOUT le projet.

AVANT : 3 fichiers chargeaient dem_dikk_lines_gps_final.json chacun de leur côté
  - context_builder.py
  - skills/question.py
  - agent/graph.py
APRÈS : un seul chargement au démarrage, partagé partout.

Usage :
  from core.network import NETWORK, VALID_LINES, get_stops, get_line_info
"""
import json
import logging

logger = logging.getLogger(__name__)

NETWORK: dict[str, dict] = {}     # "232" → {id, number, name, stops, ...}
VALID_LINES: set[str]    = set()  # {"1", "2", "8", "232", "TO1", ...}

# Index fuzzy : "terminus parcelles assainies" → "Terminus Parcelles Assainies"
_RAW: dict = {}
_ARRETS_INDEX: dict[str, str] = {}
_RAW: dict = {}

try:
    with open("dem_dikk_lines_gps_final.json", "r", encoding="utf-8") as f:
        _RAW = json.load(f)

    for _lines in _RAW.get("categories", {}).values():
        for _line in _lines:
            num = str(_line.get("number", "")).upper()
            if not num:
                continue
            NETWORK[num] = _line
            VALID_LINES.add(num)
            for stop in _line.get("stops", []):
                nom = stop.get("nom", "")
                if nom:
                    _ARRETS_INDEX[nom.lower()] = nom

    logger.info(
        f"[Network] ✅ {len(VALID_LINES)} lignes · "
        f"{len(_ARRETS_INDEX)} arrêts uniques chargés"
    )

except Exception as e:
    logger.error(f"[Network] ❌ Erreur critique chargement JSON : {e}")


def get_stops(ligne: str) -> list[dict]:
    """Retourne la liste des stops (dicts avec nom/lat/lon)."""
    return NETWORK.get(str(ligne).upper(), {}).get("stops", [])


def get_stop_names(ligne: str) -> list[str]:
    """Retourne les noms d'arrêts en minuscules pour matching."""
    return [s["nom"].lower() for s in get_stops(ligne)]


def get_line_info(ligne: str) -> dict:
    """Retourne toutes les infos d'une ligne ou {} si inconnue."""
    return NETWORK.get(str(ligne).upper(), {})


def all_stop_names() -> dict[str, str]:
    """Retourne l'index complet lower → officiel."""
    return _ARRETS_INDEX


def is_valid_line(ligne: str) -> bool:
    return str(ligne).upper() in VALID_LINES


def ambiguous_lines(prefix: str) -> list[str]:
    """
    Détecte l'ambiguïté : "16" → ["16A", "16B"]
    Retourne [] si le numéro est unique ou introuvable.
    """
    prefix = str(prefix).upper()
    matches = [l for l in VALID_LINES if l != prefix and l.startswith(prefix)]
    if matches and prefix not in VALID_LINES:
        return sorted(matches)
    return []