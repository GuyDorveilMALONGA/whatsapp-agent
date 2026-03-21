"""
agent/extractor.py — V5.0
Extraction ligne + arrêt — ZÉRO LLM.

MIGRATION V5.0 depuis V4 :
  - _load_network() supprimé — plus de lecture directe du JSON
  - NETWORK et VALID_LINES importés depuis core.network (singleton)
  - Plus de désynchronisation possible entre extractor et le reste du pipeline
  - Champ arrêt : "name" (inchangé depuis v4, core.network expose déjà "name")
  - 77 lignes · 3129 arrêts disponibles immédiatement au démarrage
"""
import re
from dataclasses import dataclass, field
from core.network import NETWORK, VALID_LINES

# ── Index dérivés du singleton ────────────────────────────

# Index numéro de base → liste de lignes (ex: "16" → ["16A", "16B"])
_BASE_TO_LIGNES: dict[str, list[str]] = {}
for _num in VALID_LINES:
    _base = re.sub(r'[A-Z\-]+$', '', _num)
    _BASE_TO_LIGNES.setdefault(_base, []).append(_num)

# Index de tous les arrêts connus (minuscules → nom officiel)
# FIX BUG-E1 : JSON v15 utilise "arrets"+"nom", pas "stops"+"name"
_ALL_ARRETS_LOWER: dict[str, str] = {}
for _line in NETWORK.values():
    for _stop in _line.get("arrets", _line.get("stops", [])):
        nom = _stop.get("nom", _stop.get("name", ""))
        if nom:
            _ALL_ARRETS_LOWER[nom.lower()] = nom
    # Indexer aussi les aliases terrain
    for _alias in _line.get("aliases_terrain", []):
        if _alias and _alias.strip():
            _ALL_ARRETS_LOWER[_alias.strip().lower()] = _alias.strip()

# ── Numéros en toutes lettres → chiffres ──────────────────

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
    ligne:           str | None
    arret:           str | None
    ligne_valide:    bool
    arret_normalise: str | None
    ambigues:        list[str] = field(default_factory=list)


def _normalize_text(text: str) -> str:
    t = text.lower()
    for mot, chiffre in sorted(_CHIFFRES.items(), key=lambda x: -len(x[0])):
        t = re.sub(r'\b' + mot + r'\b', chiffre, t)
    return t


def _find_ligne(text: str) -> tuple[str | None, list[str]]:
    text_up = text.upper()

    if "TAF TAF" in text_up:
        return "TAF TAF", []
    if "RUF" in text_up and "YENNE" in text_up:
        return "RUF-YENNE", []
    if re.search(r'\bTO1\b', text_up):
        return "TO1", []

    matches = re.findall(r'\b(\d{1,3}[A-Z]?)\b', text_up)
    matches = [m for m in matches
               if re.search(r'(?<!\d)' + re.escape(m) + r'(?!\d)', text_up)]
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
    words   = [w for w in text.lower().split() if w not in _STOPWORDS]
    cleaned = " ".join(words)

    if ligne and ligne in NETWORK:
        # FIX BUG-E2 : JSON v15 utilise "arrets"+"nom", pas "stops"+"name"
        raw_stops = NETWORK[ligne].get("arrets", NETWORK[ligne].get("stops", []))
        candidates = [
            (s.get("nom", s.get("name", "")).lower(), s.get("nom", s.get("name", "")))
            for s in raw_stops
            if s.get("nom") or s.get("name")
        ]
        # Ajouter les aliases terrain de la ligne
        for alias in NETWORK[ligne].get("aliases_terrain", []):
            if alias and alias.strip():
                candidates.append((alias.strip().lower(), alias.strip()))
    else:
        candidates = list(_ALL_ARRETS_LOWER.items())

    best_match = None
    best_score = 0
    for arret_lower, arret_officiel in candidates:
        arret_words = set(arret_lower.split())
        text_words  = set(cleaned.split())
        overlap     = arret_words & text_words
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
    normalized          = _normalize_text(text)
    ligne, ambigues     = _find_ligne(normalized.upper())
    ligne_valide        = ligne is not None and ligne in VALID_LINES
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
    if ligne not in NETWORK:
        return {"exists": False, "aller": [], "retour": [], "description": ""}
    data = NETWORK[ligne]
    # FIX BUG-E3 : JSON v15 utilise "arrets"+"nom", pas "stops"+"name"
    raw_stops  = data.get("arrets", data.get("stops", []))
    stop_names = [s.get("nom", s.get("name", "")) for s in raw_stops
                  if s.get("nom") or s.get("name")]
    desc = data.get("nom", data.get("name",
           f"{data.get('terminus_a', '')} → {data.get('terminus_b', '')}"))
    return {
        "exists":      True,
        "description": desc,
        "aller":       stop_names,
        "retour":      list(reversed(stop_names)),
    }