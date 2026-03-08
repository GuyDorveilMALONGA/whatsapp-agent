"""
agent/extractor.py
Extraction ligne + arrêt — ZÉRO LLM.
Source : dem_dikk_lines_gps_final.json (site officiel Dem Dikk · 39 lignes · 375 arrêts)
"""
import re
import json
import os
from dataclasses import dataclass, field

# ── Chargement réseau officiel ────────────────────────────

def _load_network() -> dict:
    """
    Charge dem_dikk_lines_gps_final.json depuis la racine du projet.
    Retourne un dict indexé par number (ex: "15", "16A", "RUF-YENNE").
    """
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "dem_dikk_lines_gps_final.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        network = {}
        for cat, lines in data["categories"].items():
            for line in lines:
                num = line["number"]
                # stops = liste de dicts {"nom": str, "lat": float, "lon": float}
                stop_names = [s["nom"] for s in line["stops"]]
                network[num] = {
                    "id":          line["id"],
                    "number":      num,
                    "name":        line["name"],
                    "description": f"{line['terminus_a']} → {line['terminus_b']}",
                    "category":    line["category"],
                    "terminus_a":  line["terminus_a"],
                    "terminus_b":  line["terminus_b"],
                    "arrets_aller":  stop_names,
                    "arrets_retour": list(reversed(stop_names)),
                    "stops":         stop_names,
                    "stops_gps":     line["stops"],  # GPS conservés pour dashboard
                }
        return network
    except FileNotFoundError:
        return {}

NETWORK: dict = _load_network()

# Numéros de lignes valides (ex: "15", "16A", "RUF-YENNE", "TAF TAF")
VALID_LINES: set[str] = set(NETWORK.keys())

# Index numéro de base → liste de lignes (ex: "16" → ["16A", "16B"])
_BASE_TO_LIGNES: dict[str, list[str]] = {}
for _num in VALID_LINES:
    _base = re.sub(r'[A-Z\-]+$', '', _num)
    _BASE_TO_LIGNES.setdefault(_base, []).append(_num)

# Index de tous les arrêts connus (minuscules → nom officiel)
_ALL_ARRETS_LOWER: dict[str, str] = {}
for _line in NETWORK.values():
    for _stop in _line["stops"]:
        _ALL_ARRETS_LOWER[_stop.lower()] = _stop

# Numéros en toutes lettres → chiffres
_CHIFFRES = {
    "un": "1", "une": "1", "deux": "2", "trois": "3", "quatre": "4",
    "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
    "dix": "10", "onze": "11", "douze": "12", "treize": "13",
    "quatorze": "14", "quinze": "15", "seize": "16",
    "dix-sept": "17", "dix-huit": "18", "dix-neuf": "19",
    "vingt": "20", "vingt-et-un": "21", "vingt-deux": "22",
    "vingt-trois": "23", "quarante-cinq": "45",
    "cent-vingt-et-un": "121", "deux-cent-huit": "208",
    "quatre-cent-un": "401", "trois-cent-dix-neuf": "319",
}

# Mots à ignorer lors de l'extraction d'arrêt
_STOPWORDS = {
    "bus", "le", "la", "les", "un", "une", "des", "à", "au", "aux",
    "de", "du", "en", "est", "et", "je", "tu", "il", "on", "nous",
    "vous", "ils", "que", "qui", "où", "ou", "si", "car", "voir",
    "vu", "vois", "vient", "devant", "derrière", "près", "niveau",
    "signalé", "signale", "position", "ici", "là", "maintenant",
    "ligne", "numéro", "numero",
}


@dataclass
class ExtractResult:
    ligne: str | None             # ex: "15", "16A", None si non trouvée
    arret: str | None             # ex: "Liberté 5", None si non trouvé
    ligne_valide: bool            # False si la ligne n'existe pas dans le réseau
    arret_normalise: str | None   # Nom officiel de l'arrêt si trouvé
    ambigues: list[str] = field(default_factory=list)  # ex: ["16A", "16B"] si ambigu


def _normalize_text(text: str) -> str:
    """Remplace les nombres en lettres par des chiffres."""
    t = text.lower()
    for mot, chiffre in sorted(_CHIFFRES.items(), key=lambda x: -len(x[0])):
        t = re.sub(r'\b' + mot + r'\b', chiffre, t)
    return t


def _find_ligne(text: str) -> tuple[str | None, list[str]]:
    """
    Cherche un numéro de ligne dans le texte.
    Retourne (ligne_résolue, ambigues).
    - Match exact    → (ligne, [])
    - "15" seul      → résolution silencieuse si une seule ligne → ("15", [])
    - "16" → 16A/16B → (None, ["16A", "16B"])
    - Rien           → (None, [])
    """
    text_up = text.upper()

    if "TAF TAF" in text_up:
        return "TAF TAF", []
    if "RUF" in text_up and "YENNE" in text_up:
        return "RUF-YENNE", []
    if re.search(r'\bTO1\b', text_up):
        return "TO1", []

    matches = re.findall(r'\b(\d{1,3}[A-Z]?)\b', text_up)
    matches = [m for m in matches if re.search(r'(?<!\d)' + re.escape(m) + r'(?!\d)', text_up)]
    for m in matches:
        if m in VALID_LINES:
            return m, []
        candidates = _BASE_TO_LIGNES.get(m, [])
        if len(candidates) == 1:
            return candidates[0], []
        elif len(candidates) > 1:
            return None, sorted(candidates)

    return None, []


def _find_arret(text: str, ligne: str | None) -> tuple[str | None, str | None]:
    """
    Cherche un arrêt dans le texte.
    Retourne (arret_brut, arret_normalise).
    """
    words = [w for w in text.lower().split() if w not in _STOPWORDS]
    cleaned = " ".join(words)

    if ligne and ligne in NETWORK:
        candidates = [(a.lower(), a) for a in NETWORK[ligne]["stops"]]
    else:
        candidates = list(_ALL_ARRETS_LOWER.items())

    best_match = None
    best_score = 0
    for arret_lower, arret_officiel in candidates:
        arret_words = set(arret_lower.split())
        text_words  = set(cleaned.split())
        overlap = arret_words & text_words
        if len(overlap) >= min(2, len(arret_words)) and len(overlap) > best_score:
            best_score = len(overlap)
            best_match = arret_officiel

    if best_match:
        return best_match, best_match

    pos_match = re.search(
        r'\b(à|au|devant|niveau|près de|ci)\s+(.+?)(?:\s*[,!?.]|$)',
        text, re.IGNORECASE
    )
    if pos_match:
        arret_brut = pos_match.group(2).strip()
        normalise  = _ALL_ARRETS_LOWER.get(arret_brut.lower())
        return arret_brut, normalise

    return None, None


def extract(text: str) -> ExtractResult:
    """
    Extrait ligne + arrêt depuis un message brut.
    Point d'entrée principal — utilisé par tous les skills.
    """
    normalized = _normalize_text(text)
    ligne, ambigues = _find_ligne(normalized.upper())
    ligne_valide = ligne is not None and ligne in VALID_LINES
    arret_brut, arret_normalise = _find_arret(normalized, ligne)

    if arret_brut and not arret_normalise:
        try:
            from rag.validator import validate_and_suggest
            suggestion = validate_and_suggest(arret_brut, ligne)
            if suggestion:
                arret_normalise = suggestion
        except Exception:
            pass

    return ExtractResult(
        ligne=ligne,
        arret=arret_brut,
        ligne_valide=ligne_valide,
        arret_normalise=arret_normalise,
        ambigues=ambigues,
    )


def get_arrets_ligne(ligne: str) -> dict:
    """
    Retourne les arrêts d'une ligne.
    Compatibilité : expose aller + retour même si le fichier n'a qu'une liste.
    """
    if ligne not in NETWORK:
        return {"exists": False, "aller": [], "retour": [], "description": ""}
    data = NETWORK[ligne]
    return {
        "exists":      True,
        "description": data["description"],
        "aller":       data["arrets_aller"],
        "retour":      data["arrets_retour"],
    }