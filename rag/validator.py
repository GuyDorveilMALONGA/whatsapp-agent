"""
rag/validator.py — V5 (LLM-Native)
Fuzzy matching arrêts — indépendant de extractor.py.

Source : core.network (singleton JSON)

MIGRATION V4 :
  - Aucun changement de code nécessaire.
  - core.network charge désormais routes_geometry_v4.json.
  - Le commentaire _ALIASES mis à jour : référence v4 au lieu de gps_final.
  - Recommandation V6 : migrer vers table stop_aliases Supabase

V5 :
  + SequenceMatcher → rapidfuzz.fuzz.WRatio
"""
import re
import logging
from rapidfuzz import fuzz
from core.network import all_stop_names, get_stop_names, NETWORK

logger = logging.getLogger(__name__)

SCORE_MIN          = 0.60
SCORE_CONFIRMATION = 0.45

# ── Abréviations textuelles ───────────────────────────────
_ABBREVS = {
    r"\blib5\b":    "liberté 5",
    r"\blib6\b":    "liberté 6",
    r"\blib\b":     "liberté",
    r"\bpa\b":      "parcelles assainies",
    r"\bucad\b":    "ucad",
    r"\bcinq\b":    "5",
    r"\bsix\b":     "6",
    r"\bhop\b":     "hôpital",
    r"\bmarché\b":  "marche",
    r"\bdevant\b":  "",
    r"\bprès de\b": "",
    r"\bà côté\b":  "",
    r"\bcôté\b":    "",
    r"\bface à\b":  "",
}

# ── Alias terrain Dakar → noms officiels ──────────────────
# Expressions réelles des usagers absentes du réseau officiel.
# Clé : expression normalisée (lowercase)
# Valeur : nom officiel exact dans routes_geometry_v4.json
# V6 : migrer vers table stop_aliases Supabase + UI admin
_ALIASES: dict[str, str] = {
    # Zone Yoff / Aéroport
    "senelec yoff":         "Yoff Village",
    "senelec":              "Yoff Village",
    "total yoff":           "Yoff Village",
    "mosquée yoff":         "Yoff Village",
    "marché yoff":          "Yoff Village",
    "plage yoff":           "Yoff Village",
    "yoff village":         "Yoff Village",
    "yoff":                 "Yoff",
    "aeroport":             "Terminus Aéroport LSS",
    "aéroport":             "Terminus Aéroport LSS",
    "lss":                  "Terminus Aéroport LSS",
    "asecna":               "Cité Asecna",
    "cité asecna":          "Cité Asecna",
    "pond foire":           "Pond Foire",

    # Zone Liberté / Dieuppeul
    "senelec liberté":      "Terminus Liberté 5 (Dieuppeul)",
    "total liberté":        "Terminus Liberté 5 (Dieuppeul)",
    "liberté 5":            "Terminus Liberté 5 (Dieuppeul)",
    "lib 5":                "Terminus Liberté 5 (Dieuppeul)",
    "liberté 6":            "Rond point Liberté 6",
    "lib 6":                "Rond point Liberté 6",
    "rp liberté":           "Rond point Liberté 6",
    "rp6":                  "Rond point Liberté 6",
    "dieuppeul":            "Terminus Liberté 5 (Dieuppeul)",

    # Zone Centre / Médina
    "sandaga":              "Sandaga",
    "marché sandaga":       "Sandaga",
    "tilène":               "Marché Tilène",
    "tilene":               "Marché Tilène",
    "marché tilène":        "Marché Tilène",
    "médina":               "Poste Médina",
    "medina":               "Poste Médina",
    "poste médina":         "Poste Médina",
    "hlm":                  "Marché HLM",
    "marché hlm":           "Marché HLM",
    "colobane":             "Colobane",
    "gare colobane":        "Colobane",

    # Zone UCAD / Fann
    "ucad":                 "UCAD",
    "université":           "UCAD",
    "universite":           "UCAD",
    "fann":                 "Ecole Normale",
    "hôpital fann":         "Ecole Normale",
    "hopital fann":         "Ecole Normale",
    "point e":              "Point E",

    # Zone Grand Yoff / Castor
    "grand yoff":           "Grand Yoff",
    "marché grand yoff":    "Grand Yoff",
    "castor":               "Station Castor",
    "station castor":       "Station Castor",
    "patte d'oie":          "Patte d'Oie",
    "patte doie":           "Patte d'Oie",
    "petersen":             "Petersen",

    # Zone Parcelles / Guédiawaye
    "parcelles":            "Terminus Parcelles Assainies",
    "parcelles assainies":  "Terminus Parcelles Assainies",
    "guédiawaye":           "Terminus Guédiawaye",
    "guediawaye":           "Terminus Guédiawaye",
    "dalal diam":           "Hôpital Dalal Diam",
    "hôpital dalal diam":   "Hôpital Dalal Diam",

    # Zone Banlieue
    "pikine":               "Bountou Pikine",
    "thiaroye":             "Poste Thiaroye",
    "keur massar":          "Terminus Keur Massar",
    "ker massar":           "Terminus Keur Massar",
    "rufisque":             "Terminus Rufisque",
    "ouakam":               "Terminus Ouakam",
    "ngor":                 "Ngor Village",
    "ngor village":         "Ngor Village",
    "almadies":             "Terminus Almadies",

    # Zone Plateau / Centre-ville
    "palais":               "Terminus Palais 2",
    "palais 2":             "Terminus Palais 2",
    "palais 1":             "Palais 1",
    "indépendance":         "Place de l'Indépendance",
    "independance":         "Place de l'Indépendance",
    "place indépendance":   "Place de l'Indépendance",
    "leclerc":              "Terminus Leclerc",
    "terminus leclerc":     "Terminus Leclerc",
    "pompiers":             "Sapeur Pompiers",
    "jet d'eau":            "Jet d'eau",
    "jet deau":             "Jet d'eau",
    "foire":                "Foire",
    "rond point foire":     "Foire",
    "vdn":                  "VDN",
}


def _clean(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    for pattern, replacement in _ABBREVS.items():
        t = re.sub(pattern, replacement, t)
    return re.sub(r"\s+", " ", t).strip()


def _apply_aliases(cleaned: str) -> str | None:
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]
    for alias, officiel in _ALIASES.items():
        if alias in cleaned or cleaned in alias:
            return officiel
    return None


def _similarity(a: str, b: str) -> float:
    return fuzz.WRatio(a, b) / 100.0


def normalize_arret(arret_brut: str, ligne: str | None = None) -> dict:
    if not arret_brut or len(arret_brut.strip()) < 2:
        return {"found": False, "arret_officiel": None,
                "score": 0.0, "needs_confirmation": False}

    cleaned = _clean(arret_brut)

    # ── Niveau 1 : Alias terrain ──────────────────────────
    alias_result = _apply_aliases(cleaned)
    if alias_result:
        logger.debug(f"[Validator] Alias match: '{arret_brut}' → '{alias_result}'")
        return {"found": True, "arret_officiel": alias_result,
                "score": 1.0, "needs_confirmation": False}

    # ── Niveau 2 : Fuzzy sur arrêts de la ligne ───────────
    candidates: dict[str, str] = {}
    if ligne:
        ligne_up = str(ligne).upper()
        if ligne_up in NETWORK:
            for stop in NETWORK[ligne_up].get("stops", []):
                # v4 : champ "name"
                nom = stop.get("name", "")
                if nom:
                    candidates[nom.lower()] = nom

    # ── Niveau 3 : Fuzzy sur tous les arrêts ─────────────
    if not candidates:
        candidates = all_stop_names()

    best_arret, best_score = None, 0.0
    for arret_lower, arret_officiel in candidates.items():
        score = _similarity(cleaned, arret_lower)
        if score > best_score:
            best_score = score
            best_arret = arret_officiel

    if best_score >= SCORE_MIN:
        return {"found": True, "arret_officiel": best_arret,
                "score": round(best_score, 2), "needs_confirmation": False}
    elif best_score >= SCORE_CONFIRMATION:
        return {"found": False, "arret_officiel": best_arret,
                "score": round(best_score, 2), "needs_confirmation": True}
    else:
        return {"found": False, "arret_officiel": None,
                "score": round(best_score, 2), "needs_confirmation": False}


def validate_and_suggest(arret_brut: str, ligne: str | None = None) -> str | None:
    result = normalize_arret(arret_brut, ligne)
    return result["arret_officiel"] if result["found"] else None


def confirmation_message(arret_brut: str, suggestion: str, langue: str = "fr") -> str:
    if langue == "wolof":
        return (
            f"Danga wax *{arret_brut}* — "
            f"maa ngi xam *{suggestion}* ? Tontu 'waaw' walla wax arrêt bi."
        )
    return f"Tu veux dire *{suggestion}* ? Réponds 'oui' ou précise l'arrêt."