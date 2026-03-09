"""
services/language.py — V2
Détection de langue SANS LLM.
langdetect + liste de mots-clés wolof/pulaar pour les cas ratés.

FIX V2 :
  Seuil wolof/pulaar abaissé à 1 mot fort.
  "waaw" seul → wolof. "dafa" seul → wolof.
  Liste de mots FORTS séparée de la liste générale.
"""
from langdetect import detect, LangDetectException

# Mots FORTS wolof — 1 seul suffit pour déclencher Gemini
WOLOF_STRONG = {
    "waaw", "dafa", "xam", "bëgg", "jërejëf", "naka", "ndax",
    "sëde", "dinu", "ngi", "rekk", "yëgël", "lan", "wax",
    "nga", "naa", "dina", "danu", "dinañu", "jamm", "xarit",
    "mbokk", "téranga", "toubab", "ñëw", "dem", "jël",
}

# Mots courants wolof — 2 requis (présents dans d'autres langues)
WOLOF_COMMON = {
    "maa", "bi", "yi", "ba", "ci", "fi", "si", "ak", "bu",
    "mu", "ñu", "ko", "man", "sunu", "sama", "yow", "buur",
    "xale", "jaay", "dëkk",
}

PULAAR_STRONG = {
    "jooni", "jokku", "yimaabe", "maayo", "nguurndam", "hol",
}

PULAAR_COMMON = {
    "ko", "mi", "on", "oo", "en", "nde", "dow", "wuro",
    "tan", "fof", "dum", "kam", "mo", "be", "noon",
    "alaa", "haa",
}


def detect_language(text: str) -> str:
    """
    Retourne : 'fr', 'en', 'wolof', 'pulaar', 'unknown'

    Priorité :
    1. 1 mot fort wolof → wolof
    2. 2+ mots courants wolof → wolof
    3. 1 mot fort pulaar → pulaar
    4. 2+ mots courants pulaar → pulaar
    5. langdetect fallback
    """
    if not text or len(text.strip()) < 2:
        return "unknown"

    words = set(text.lower().split())

    # Wolof fort : 1 mot suffit
    if words & WOLOF_STRONG:
        return "wolof"

    # Wolof courant : 2 mots requis
    if len(words & WOLOF_COMMON) >= 2:
        return "wolof"

    # Pulaar fort : 1 mot suffit
    if words & PULAAR_STRONG:
        return "pulaar"

    # Pulaar courant : 2 mots requis
    if len(words & PULAAR_COMMON) >= 2:
        return "pulaar"

    # Fallback langdetect
    try:
        code = detect(text)
        return {"fr": "fr", "en": "en", "ff": "pulaar", "wo": "wolof"}.get(code, "unknown")
    except LangDetectException:
        return "unknown"