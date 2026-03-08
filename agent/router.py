"""
agent/router.py — V3.1
Intent Gateway — 4 niveaux de classification.

FIX #3 : Cache key contextuelle (message + état session)
"""
import re
import logging
from dataclasses import dataclass

from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)

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
        (r"\bwaar\b", 0.7),
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
        (r"\b(quelle\s+ligne|prends?\s+quelle\s+ligne)\b", 0.7),
        (r"\b(itinéraire|trajet|chemin)\b", 0.8),
        (r"\b(je\s+vais|je\s+veux\s+(aller|me\s+rendre))\b", 0.5),
        (r"\bje\s+veux\s+(à|au)\b", 0.5),
        (r"\bpour\s+aller\b", 0.6),
        (r"\bje\s+suis\s+à\b.{2,40}\bje\s+veux\b", 0.9),
        (r"\b(depuis|de)\b.{2,30}\b(jusqu|vers|à|pour)\b", 0.7),
        (r"\b(→|->|➔)\b", 0.6),
        (r"\b(dem\s+ci|dem\s+fa|def\s+naa\s+dem)\b", 0.8),
    ],
}

_SCORE_THRESHOLD = 0.85


def _apply_penalties(text: str, scores: dict[str, float]) -> dict[str, float]:
    t = text.lower()
    je_suis = re.search(r"\bje\s+(suis|me\s+trouve)\s+(à|au|ici|là)\b", t)
    has_bus  = re.search(r"\bbus\b", t)
    if je_suis and not has_bus:
        scores["signalement"] = scores.get("signalement", 0) * 0.2
        scores["itineraire"]  = min(scores.get("itineraire", 0) + 0.4, 1.0)
    quartier = re.search(r"\b(liberté|hlm|sacré[- ]cœur|grand[- ]yoff|parcelles)\s+\d+\b", t)
    if quartier and not has_bus:
        scores["signalement"] = scores.get("signalement", 0) * 0.15
    if re.search(r"\b(tu\s+es|t[' ]es|chatgpt|gpt|ia|robot|bot|qui\s+es[- ]tu)\b", t):
        scores["out_of_scope"] = 1.0
    return scores


def _fast_classify(text: str) -> tuple[str, float]:
    t = text.lower()
    scores: dict[str, float] = {}
    for intent, rules in _SCORING_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            if re.search(pattern, t):
                score += weight
        scores[intent] = min(score, 1.0)
    scores = _apply_penalties(t, scores)
    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]
    if best_score < 0.3:
        return "out_of_scope", 1.0
    logger.debug(f"[Router] Scores: {scores} → {best_intent} ({best_score:.2f})")
    return best_intent, best_score


def _is_identity_question(text: str) -> bool:
    t = text.lower()
    patterns = [
        r"\b(chatgpt|gpt-?\d*|openai|claude|gemini|copilot)\b",
        r"\b(tu\s+es\s+(qui|quoi|un\s+(robot|bot|ia)))\b",
        r"\b(c[' ]est\s+quoi\s+(xëtu|xetu|sëtu|setu|toi))\b",
        r"\b(qui\s+(es[- ]tu|t[' ]es))\b",
    ]
    return any(re.search(p, t) for p in patterns)


@dataclass
class RouteResult:
    intent: str
    raw_text: str
    normalized_text: str
    confiance: float
    source: str


def route(text: str, session_state: str | None = None) -> RouteResult:
    """
    FIX #3 : session_state passé au cache pour éviter les collisions.
    Ex: "liberté 5" en flow attente_arret ≠ "liberté 5" message libre.
    """
    normalized = normalize(text)
    cache_key  = normalize_for_cache(text)

    if _is_identity_question(normalized):
        return RouteResult(
            intent="out_of_scope",
            raw_text=text,
            normalized_text=normalized,
            confiance=1.0,
            source="identity"
        )

    # Cache avec état session
    cached = intent_cache.get(cache_key, session_state)
    if cached:
        return RouteResult(
            intent=cached,
            raw_text=text,
            normalized_text=normalized,
            confiance=1.0,
            source="cache"
        )

    intent, score = _fast_classify(normalized)

    if score >= _SCORE_THRESHOLD:
        intent_cache.set(cache_key, intent, session_state)
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


async def route_async(text: str, history: list | None = None,
                      session_state: str | None = None) -> RouteResult:
    result = route(text, session_state)

    if result.source in ("cache", "regex", "identity"):
        return result

    logger.info(f"[Router] Score faible ({result.confiance:.2f}) → LLM classify")
    try:
        from agent.llm_brain import classify_intent
        llm_intent = await classify_intent(text=result.normalized_text, history=history)
        if llm_intent:
            intent_cache.set(normalize_for_cache(text), llm_intent, session_state)
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
