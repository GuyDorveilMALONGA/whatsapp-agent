"""
agent/router.py
Intent Gateway — 4 niveaux de classification.

Niveau 0 : Normalisation (normalizer.py)
Niveau 1 : Cache d'intention (intent_cache.py)
Niveau 2 : Fast classifier (regex + scoring)
Niveau 3 : LLM classifier fallback (si score < 0.85)

Règle absolue : les skills ne sont jamais appelés ici.
Le router retourne uniquement une intention + confiance.
"""
import re
import logging
from dataclasses import dataclass

from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)

# ── Scoring keywords par intention ───────────────────────
# Chaque règle : (pattern, poids)
# Score final = somme des poids matchés

_SCORING_RULES: dict[str, list[tuple[str, float]]] = {

    "signalement": [
        (r"\bbus\b", 0.3),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.3),
        (r"\b(à|au|devant|niveau|près de|derrière|avant|ci)\b", 0.4),
        (r"\b(liberté|hlm|gare|marché|mosquée|palais|parcelles)\b", 0.2),
        (r"\b(vu|vois|voir|vient|passe|passé|là|ici)\b", 0.2),
    ],

    "question": [
        (r"\b(où|ou|woon|ngelaw|est\s+où)\b", 0.5),
        (r"\b(quand|combien|minutes?|heures?)\b", 0.4),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.2),
        (r"\b(bus|ligne)\b", 0.2),
        (r"\?", 0.2),
        (r"\b(arriver|venir|passer|attendre)\b", 0.3),
    ],

    "abonnement": [
        (r"\b(préviens?|prévenez|alerte|alerter|abonne|surveille|notifie)\b", 0.7),
        (r"\b(moi|me)\b", 0.2),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.1),
        (r"\bwaar\b", 0.7),                    # wolof
    ],

    "escalade": [
        (r"\b(humain|agent|opérateur|responsable)\b", 0.8),
        (r"\b(parler\s+à|contacter)\b", 0.6),
        (r"\b(problème|réclamation|plainte|incident)\b", 0.5),
        (r"\b(ne\s+marche\s+pas|ne\s+fonctionne\s+pas)\b", 0.6),
    ],

    "liste_arrets": [
        (r"\b(arrêts?|stations?)\b", 0.5),
        (r"\b(liste|lister|montre|tous)\b", 0.3),
        (r"\b(passe\s+par|par\s+où)\b", 0.6),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.2),
    ],

    "itineraire": [
        (r"\b(comment\s+(aller|arriver|me\s+rendre))\b", 0.8),
        (r"\b(quel\s+bus\s+pour|quel\s+bus\s+prendre)\b", 0.8),
        (r"\b(itinéraire|trajet|chemin)\b", 0.8),
        (r"\b(je\s+(suis|me\s+trouve|suis\s+à))\b", 0.3),
        (r"\b(je\s+vais|je\s+veux\s+aller|je\s+veux\s+me\s+rendre)\b", 0.5),
        (r"\b(depuis|de)\b.{2,30}\b(jusqu|vers|à|pour)\b", 0.7),
        (r"\b(→|->|➔)\b", 0.6),
        # Wolof
        (r"\b(dem\s+ci|dem\s+fa|def\s+naa\s+dem)\b", 0.8),
    ],
}

_SCORE_THRESHOLD = 0.85  # En dessous → LLM prend la main


def _fast_classify(text: str) -> tuple[str, float]:
    """
    Calcule un score pour chaque intention.
    Retourne (meilleure_intention, score).
    """
    t = text.lower()
    scores: dict[str, float] = {}

    for intent, rules in _SCORING_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            if re.search(pattern, t):
                score += weight
        scores[intent] = min(score, 1.0)

    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    if best_score < 0.3:
        return "out_of_scope", 1.0

    logger.debug(f"[Router] Scores: {scores} → {best_intent} ({best_score:.2f})")
    return best_intent, best_score


@dataclass
class RouteResult:
    intent: str
    raw_text: str
    normalized_text: str
    confiance: float
    source: str  # "cache" | "regex" | "regex_low" | "llm"


def route(text: str) -> RouteResult:
    """
    Version synchrone — utilisée en fallback si route_async non disponible.
    """
    normalized = normalize(text)
    cache_key  = normalize_for_cache(text)

    # Niveau 1 — Cache
    cached = intent_cache.get(cache_key)
    if cached:
        logger.debug(f"[Router] Cache HIT → {cached}")
        return RouteResult(
            intent=cached,
            raw_text=text,
            normalized_text=normalized,
            confiance=1.0,
            source="cache"
        )

    # Niveau 2 — Fast classifier
    intent, score = _fast_classify(normalized)

    if score >= _SCORE_THRESHOLD:
        intent_cache.set(cache_key, intent)
        return RouteResult(
            intent=intent,
            raw_text=text,
            normalized_text=normalized,
            confiance=score,
            source="regex"
        )

    return RouteResult(
        intent=intent,
        raw_text=text,
        normalized_text=normalized,
        confiance=score,
        source="regex_low"
    )


async def route_async(text: str, history: list | None = None) -> RouteResult:
    """
    Version async avec fallback LLM si confiance insuffisante.
    C'est cette fonction qu'on appelle dans main.py.
    """
    result = route(text)

    if result.source in ("cache", "regex"):
        return result

    # Niveau 3 — LLM classifier
    logger.info(f"[Router] Score faible ({result.confiance:.2f}) → LLM classify")
    try:
        from agent.llm_brain import classify_intent
        llm_intent = await classify_intent(
            text=result.normalized_text,
            history=history
        )
        if llm_intent:
            cache_key = normalize_for_cache(text)
            intent_cache.set(cache_key, llm_intent)
            logger.info(f"[Router] LLM → {llm_intent}")
            return RouteResult(
                intent=llm_intent,
                raw_text=text,
                normalized_text=result.normalized_text,
                confiance=0.95,
                source="llm"
            )
    except Exception as e:
        logger.error(f"[Router] LLM classify failed: {e}")

    return result