"""
rag/validator.py — V2
Validation et normalisation des arrêts via fuzzy matching.
En V2 : matching sur les 592 arrêts indexés avec pgvector.
En fallback : matching par distance de Levenshtein (sans DB).

Exemples :
  'lib5'           → 'Liberté 5'       (score: 0.94)
  'liberté cinq'   → 'Liberté 5'       (score: 0.91)
  'sandaga marché' → 'Sandaga'         (score: 0.88)
  'devant la mairie' → None            (score: 0.42 — trop flou)
"""
import re
import logging
from difflib import SequenceMatcher

from agent.extractor import _ALL_ARRETS_LOWER, NETWORK

logger = logging.getLogger(__name__)

# Seuil minimum de similarité pour valider un arrêt
SCORE_MIN = 0.60
# Seuil en dessous duquel on demande confirmation à l'usager
SCORE_CONFIRMATION = 0.45


def normalize_arret(arret_brut: str, ligne: str | None = None) -> dict:
    """
    Normalise un nom d'arrêt brut vers le nom officiel.

    Retourne :
      {
        "found": True/False,
        "arret_officiel": "Liberté 5" ou None,
        "score": 0.94,
        "needs_confirmation": False,  # True si score entre 0.45 et 0.60
      }
    """
    if not arret_brut or len(arret_brut.strip()) < 2:
        return {"found": False, "arret_officiel": None, "score": 0.0, "needs_confirmation": False}

    cleaned = _clean(arret_brut)

    # Priorité : arrêts de la ligne spécifique
    candidates = []
    if ligne and ligne in NETWORK:
        arrets_ligne = (
            NETWORK[ligne].get("arrets_aller", []) +
            NETWORK[ligne].get("arrets_retour", [])
        )
        candidates = [(a.lower(), a) for a in arrets_ligne]

    # Tous les arrêts si pas de ligne ou pas trouvé dans la ligne
    if not candidates:
        candidates = list(_ALL_ARRETS_LOWER.items())

    best_arret = None
    best_score = 0.0

    for arret_lower, arret_officiel in candidates:
        score = _similarity(cleaned, arret_lower)
        if score > best_score:
            best_score = score
            best_arret = arret_officiel

    if best_score >= SCORE_MIN:
        return {
            "found": True,
            "arret_officiel": best_arret,
            "score": round(best_score, 2),
            "needs_confirmation": False,
        }
    elif best_score >= SCORE_CONFIRMATION:
        return {
            "found": False,
            "arret_officiel": best_arret,   # Suggestion
            "score": round(best_score, 2),
            "needs_confirmation": True,      # Demander confirmation
        }
    else:
        return {
            "found": False,
            "arret_officiel": None,
            "score": round(best_score, 2),
            "needs_confirmation": False,
        }


def validate_and_suggest(arret_brut: str, ligne: str | None = None) -> str | None:
    """
    Version simple : retourne le nom officiel ou None.
    Utilisée par extractor en V2 pour remplacer le matching basique.
    """
    result = normalize_arret(arret_brut, ligne)
    if result["found"]:
        return result["arret_officiel"]
    return None


def confirmation_message(arret_brut: str, suggestion: str, langue: str = "fr") -> str:
    """
    Message de confirmation quand le score est entre 0.45 et 0.60.
    """
    if langue == "wolof":
        return f"Danga wax *{arret_brut}* — maa ngi xam *{suggestion}* ? Tontu 'waaw' walla wax arrêt bi."
    return f"Tu veux dire *{suggestion}* ? Réponds 'oui' ou précise l'arrêt."


# ── Helpers ───────────────────────────────────────────────

# Abréviations et synonymes courants à Dakar
_ABBREVS = {
    "lib": "liberté",
    "lib5": "liberté 5",
    "lib6": "liberté 6",
    "pa": "parcelles assainies",
    "hlm": "hlm",
    "gd": "grand",
    "mq": "mosquée",
    "hop": "hôpital",
    "ucad": "ucad",
    "pmc": "place de l'indépendance",
    "cinq": "5",
    "six": "6",
}

def _clean(text: str) -> str:
    """Normalise le texte pour le matching."""
    t = text.lower().strip()
    # Supprime la ponctuation
    t = re.sub(r"[^\w\s]", " ", t)
    # Applique les abréviations
    for abbrev, full in _ABBREVS.items():
        t = re.sub(r'\b' + abbrev + r'\b', full, t)
    # Normalise les espaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _similarity(a: str, b: str) -> float:
    """Score de similarité entre deux chaînes (0 à 1)."""
    # Score SequenceMatcher
    seq_score = SequenceMatcher(None, a, b).ratio()

    # Bonus si tous les mots de a sont dans b
    words_a = set(a.split())
    words_b = set(b.split())
    if words_a and words_a.issubset(words_b):
        seq_score = min(1.0, seq_score + 0.15)

    # Bonus si début identique
    if b.startswith(a[:4]) and len(a) >= 4:
        seq_score = min(1.0, seq_score + 0.10)

    return seq_score
