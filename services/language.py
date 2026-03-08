"""
services/language.py
Détection de langue SANS LLM.
langdetect + liste de mots-clés wolof/pulaar pour les cas ratés.
"""
from langdetect import detect, LangDetectException

# Mots fréquents en wolof — langdetect les rate souvent
WOLOF_KEYWORDS = {
    "xam", "dem", "jëf", "waaw", "dafa", "maa", "ngi", "rekk",
    "bëgg", "jërejëf", "yëgël", "naka", "lan", "ndax", "wax",
    "dëkk", "buur", "xale", "jaay", "yow", "man", "sunu", "sama",
    "bi", "yi", "ba", "ci", "fi", "si", "ak", "bu", "mu",
    "nga", "naa", "dina", "danu", "dinañu", "ñu", "ko",
    "toubab", "mbokk", "xarit", "jamm", "téranga"
}

# Mots fréquents en pulaar
PULAAR_KEYWORDS = {
    "ko", "mi", "on", "oo", "en", "nde", "dow", "wuro",
    "hol", "to", "tan", "fof", "dum", "kam", "mo", "be",
    "jooni", "noon", "waaw", "alaa", "haa", "jokku",
    "yimaabe", "maayo", "nguurndam"
}


def detect_language(text: str) -> str:
    """
    Retourne : 'fr', 'en', 'wolof', 'pulaar', 'unknown'
    """
    if not text or len(text.strip()) < 2:
        return "unknown"

    text_lower = text.lower()
    words = set(text_lower.split())

    # Wolof : si 2+ mots-clés présents → wolof
    wolof_hits = words & WOLOF_KEYWORDS
    if len(wolof_hits) >= 2:
        return "wolof"

    # Pulaar : si 2+ mots-clés présents → pulaar
    pulaar_hits = words & PULAAR_KEYWORDS
    if len(pulaar_hits) >= 2:
        return "pulaar"

    # Fallback langdetect
    try:
        code = detect(text)
        mapping = {
            "fr": "fr",
            "en": "en",
            "ff": "pulaar",   # Fula/Fulah
            "wo": "wolof",
        }
        return mapping.get(code, "unknown")
    except LangDetectException:
        return "unknown"
