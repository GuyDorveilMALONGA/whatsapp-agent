"""
rag/validator.py — V3 (LLM-Native)
Fuzzy matching arrêts — indépendant de extractor.py.

Source : core.network (singleton JSON)
Exemples :
  'lib5'             → 'Liberté 5'     (0.94)
  'devant le marché' → 'Sandaga'       (0.71) selon contexte ligne
  'à côté de ucad'   → 'UCAD'          (0.88)
  'pharmacie'        → None            (0.38 — trop flou)
"""
import re
import logging
from difflib import SequenceMatcher
from core.network import all_stop_names, get_stop_names, NETWORK

logger = logging.getLogger(__name__)

SCORE_MIN          = 0.60   # Validation automatique
SCORE_CONFIRMATION = 0.45   # Demande confirmation à l'usager

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


def _clean(text: str) -> str:
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    for pattern, replacement in _ABBREVS.items():
        t = re.sub(pattern, replacement, t)
    return re.sub(r"\s+", " ", t).strip()


def _similarity(a: str, b: str) -> float:
    score = SequenceMatcher(None, a, b).ratio()
    words_a, words_b = set(a.split()), set(b.split())
    if words_a and words_a.issubset(words_b):
        score = min(1.0, score + 0.15)
    if len(a) >= 4 and b.startswith(a[:4]):
        score = min(1.0, score + 0.10)
    return score


def normalize_arret(arret_brut: str, ligne: str | None = None) -> dict:
    """
    Normalise un nom d'arrêt brut vers le nom officiel.
    Priorité : arrêts de la ligne spécifique → tous les arrêts.

    Retourne :
      {
        "found": bool,
        "arret_officiel": str | None,
        "score": float,
        "needs_confirmation": bool,
      }
    """
    if not arret_brut or len(arret_brut.strip()) < 2:
        return {"found": False, "arret_officiel": None,
                "score": 0.0, "needs_confirmation": False}

    cleaned = _clean(arret_brut)

    # Priorité : arrêts de la ligne spécifique
    candidates: dict[str, str] = {}
    if ligne:
        ligne_up = str(ligne).upper()
        if ligne_up in NETWORK:
            for stop in NETWORK[ligne_up].get("stops", []):
                nom = stop.get("nom", "")
                if nom:
                    candidates[nom.lower()] = nom

    # Fallback : tous les arrêts
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
    """Retourne le nom officiel ou None."""
    result = normalize_arret(arret_brut, ligne)
    return result["arret_officiel"] if result["found"] else None


def confirmation_message(arret_brut: str, suggestion: str, langue: str = "fr") -> str:
    if langue == "wolof":
        return (
            f"Danga wax *{arret_brut}* — "
            f"maa ngi xam *{suggestion}* ? Tontu 'waaw' walla wax arrêt bi."
        )
    return f"Tu veux dire *{suggestion}* ? Réponds 'oui' ou précise l'arrêt."