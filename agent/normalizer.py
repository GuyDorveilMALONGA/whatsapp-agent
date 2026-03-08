"""
agent/normalizer.py
Niveau 0 — Normalisation du message brut.
Appelé avant tout traitement (router, extractor, LLM).
Coût : < 0.5ms, zéro dépendance externe.
"""
import re
import unicodedata


# Corrections typiques : collages, inversions, fautes fréquentes
_CORRECTIONS = {
    r"\bbus(\d)": r"bus \1",        # "bus15" → "bus 15"
    r"\b(\d)bus\b": r"bus \1",      # "15bus" → "bus 15"
    r"\bbuss\b": "bus",             # "buss" → "bus"
    r"\bligne(\d)": r"ligne \1",    # "ligne15" → "ligne 15"
    r"\b(\d{1,3})([A-Z])\b": r"\1\2",  # garde "15R" intact
}

# Mots wolof normalisés vers forme standard
_WOLOF_NORM = {
    "buss": "bus",
    "bous": "bus",
    "ngelaw": "est où",
    "fi ngelaw": "est où",
    "woon": "était",
    "jëf": "signaler",
}


def normalize(text: str) -> str:
    """
    Normalise un message brut :
    1. Strip + lowercase
    2. Correction collages (bus15 → bus 15)
    3. Normalisation wolof
    4. Espaces multiples
    """
    if not text:
        return ""

    t = text.strip()

    # Corrections typographiques
    for pattern, replacement in _CORRECTIONS.items():
        t = re.sub(pattern, replacement, t, flags=re.IGNORECASE)

    # Normalisation wolof
    for mot, remplacement in _WOLOF_NORM.items():
        t = re.sub(r'\b' + re.escape(mot) + r'\b', remplacement, t, flags=re.IGNORECASE)

    # Espaces multiples → simple
    t = re.sub(r'\s+', ' ', t).strip()

    return t


def normalize_for_cache(text: str) -> str:
    """
    Version agressive pour le cache d'intention :
    lowercase + sans accents + sans ponctuation + normalize.
    Permet de matcher "Où est le 15 ?" == "ou est le 15"
    """
    t = normalize(text).lower()

    # Supprime accents
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')

    # Supprime ponctuation sauf chiffres et lettres
    t = re.sub(r'[^\w\s]', '', t)

    # Espaces multiples
    t = re.sub(r'\s+', ' ', t).strip()

    return t
