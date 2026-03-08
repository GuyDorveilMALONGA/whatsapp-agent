"""
agent/router.py
Routing déterministe — ZÉRO appel LLM.
Regex + mots-clés uniquement. Rapide, fiable, gratuit.
"""
import re
from dataclasses import dataclass

# ── Patterns par intention ────────────────────────────────

# Signalement : "bus X à Y", "le X est à Y", "X niveau Y", etc.
_SIGNALEMENT_PATTERNS = [
    r"\bbus\s+(\w+)\s+(à|au|devant|niveau|près de|derrière|avant)\b",
    r"\b(le|la)\s+(\w+)\s+(est\s+)?(à|au|devant|niveau)\b",
    r"\b(\w+)\s+ci\s+\w+\b",        # wolof : "bus bi ci liberté"
    r"\bbus\s+\w+\s+\w+\b",         # "bus 15 liberté"
]

# Question : "où est", "le X est où", "quand arrive", etc.
_QUESTION_PATTERNS = [
    r"\b(où|ou)\b.*(bus|ligne)",
    r"\bbus\b.*(où|ou|ici|woon|fi)\b",
    r"\b(le|la)\s+\w+\s+(est\s+)?(où|ou)\b",
    r"\b(quand|combien).*(bus|ligne|arriver|venir)",
    r"\b(quel\s+bus|quelle\s+ligne)\b",
    r"\bbus\b.*\?",
    r"\w+\s+(fi\s+)?ngelaw\b",      # wolof : "bus bi fi ngelaw ?"
    r"\bnak(a|u)\b.*bus",           # wolof : "naka bus bi ?"
]

# Abonnement : "préviens-moi", "alerte", "surveille", etc.
_ABONNEMENT_PATTERNS = [
    r"\b(préviens?[-\s]moi|prévenez[-\s]moi)\b",
    r"\b(alerte[rz]?[-\s]moi|alertes?)\b",
    r"\b(abonne[rz]?[-\s]moi|abonnement)\b",
    r"\b(surveille[rz]?|surveille)\b",
    r"\b(notifie[rz]?[-\s]moi|notification)\b",
    r"\bwaar\b.*bus",               # wolof : "waar ma bus bi"
]

# Escalade : demande un humain
_ESCALADE_PATTERNS = [
    r"\b(humain|agent|opérateur|responsable|service\s+client)\b",
    r"\b(parler\s+à|contacter\s+un)\b",
    r"\b(problème|réclamation|plainte|incident)\b",
    r"\b(ça\s+ne\s+marche\s+pas|ne\s+fonctionne\s+pas)\b",
]

# Lister arrêts : "quels sont les arrêts", "liste les arrêts"
_LISTE_ARRETS_PATTERNS = [
    r"\b(arrêts?|stations?)\s+(de\s+)?(la\s+)?(ligne\s+)?\w+",
    r"\b(liste|lister|montre)\s+(les\s+)?(arrêts?|stations?)\b",
    r"\b(passe\s+par|par\s+où\s+passe)\b",
]


def _match(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in patterns)


@dataclass
class RouteResult:
    intent: str   # signalement | question | abonnement | escalade | liste_arrets | out_of_scope
    raw_text: str


def route(text: str) -> RouteResult:
    """
    Classifie l'intention d'un message.
    Ordre d'évaluation : signalement > abonnement > liste_arrets > question > escalade > out_of_scope
    """
    # Signalement en priorité : contient un verbe de position + numéro
    if _match(text, _SIGNALEMENT_PATTERNS):
        # Double vérification : doit contenir un chiffre ou "BRT" (numéro de ligne)
        if re.search(r"\b(\d{1,3}[A-Z]?|BRT|TER)\b", text, re.IGNORECASE):
            return RouteResult(intent="signalement", raw_text=text)

    # Abonnement
    if _match(text, _ABONNEMENT_PATTERNS):
        return RouteResult(intent="abonnement", raw_text=text)

    # Liste des arrêts d'une ligne
    if _match(text, _LISTE_ARRETS_PATTERNS):
        return RouteResult(intent="liste_arrets", raw_text=text)

    # Question sur position/horaire d'un bus
    if _match(text, _QUESTION_PATTERNS):
        return RouteResult(intent="question", raw_text=text)

    # Escalade
    if _match(text, _ESCALADE_PATTERNS):
        return RouteResult(intent="escalade", raw_text=text)

    # Hors sujet
    return RouteResult(intent="out_of_scope", raw_text=text)
