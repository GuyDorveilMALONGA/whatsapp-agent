"""
agent/router.py — V3
Intent Gateway — 4 niveaux de classification.

Niveau 0 : Normalisation (normalizer.py)
Niveau 1 : Cache d'intention (intent_cache.py)
Niveau 2 : Fast classifier (regex + scoring + pénalités contextuelles)
Niveau 3 : LLM classifier fallback (si score < 0.85)

Nouveautés V3 :
- Pénalités contextuelles : "je suis à X" sans numéro → pénalise signalement
- Boost question si message commence par "je suis à / je me trouve"
- Protection contre les faux signalements en contexte de réponse
"""
import re
import logging
from dataclasses import dataclass

from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)

# ── Scoring keywords par intention ───────────────────────

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
        (r"\b(itinéraire|trajet|chemin)\b", 0.8),
        (r"\b(je\s+(suis|me\s+trouve)\s+(?:à|au))\b", 0.3),
        (r"\b(je\s+vais|je\s+veux\s+aller|je\s+veux\s+me\s+rendre)\b", 0.5),
        (r"\b(depuis|de)\b.{2,30}\b(jusqu|vers|à|pour)\b", 0.7),
        (r"\b(→|->|➔)\b", 0.6),
        (r"\b(dem\s+ci|dem\s+fa|def\s+naa\s+dem)\b", 0.8),
    ],
}

_SCORE_THRESHOLD = 0.85


# ── Pénalités contextuelles ───────────────────────────────
# Appliquées APRÈS le scoring de base pour corriger les ambiguïtés

def _apply_penalties(text: str, scores: dict[str, float]) -> dict[str, float]:
    """
    Applique des pénalités/boosts contextuels pour éviter les faux positifs.

    Cas couverts :
    1. "Je suis à X" sans numéro de bus → probablement réponse à une question,
       pas un signalement. Pénalise signalement, booste itineraire/question.
    2. "Je suis à liberté 5" — le "5" est un numéro de rue, pas une ligne.
       Sans le mot "bus" explicite, score signalement pénalisé.
    3. Message très court sans numéro → probablement hors scope ou réponse.
    """
    t = text.lower()

    # Cas 1 : "je suis à X" ou "je me trouve à X" sans le mot "bus"
    # → l'usager donne sa position, pas un signalement
    je_suis_pattern = re.search(r"\bje\s+(suis|me\s+trouve)\s+(à|au|ici|là)\b", t)
    has_bus_keyword = re.search(r"\bbus\b", t)

    if je_suis_pattern and not has_bus_keyword:
        # Forte pénalité sur signalement
        scores["signalement"] = scores.get("signalement", 0) * 0.2
        # Boost itinéraire (l'usager donne son point de départ)
        scores["itineraire"] = min(scores.get("itineraire", 0) + 0.4, 1.0)
        logger.debug("[Router] Pénalité 'je suis à' sans 'bus' → signalement pénalisé")

    # Cas 2 : "je suis à liberté X" — le chiffre est un numéro de rue/quartier
    # Pattern très spécifique aux quartiers de Dakar : "liberté 5", "hlm 6", etc.
    quartier_pattern = re.search(
        r"\b(liberté|hlm|sacré[- ]cœur|grand[- ]yoff|parcelles)\s+\d+\b", t
    )
    if quartier_pattern and not has_bus_keyword:
        scores["signalement"] = scores.get("signalement", 0) * 0.15
        logger.debug("[Router] Pénalité quartier numéroté sans 'bus'")

    # Cas 3 : question d'identité → out_of_scope avec boost
    identite_pattern = re.search(
        r"\b(tu\s+es|t[' ]es|c[' ]est\s+quoi|qui\s+es[- ]tu|chatgpt|gpt|ia|robot|bot)\b", t
    )
    if identite_pattern:
        scores["out_of_scope"] = 1.0
        logger.debug("[Router] Détection question identité → out_of_scope")

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

    # Applique les pénalités contextuelles
    scores = _apply_penalties(t, scores)

    best_intent = max(scores, key=scores.get)
    best_score  = scores[best_intent]

    if best_score < 0.3:
        return "out_of_scope", 1.0

    logger.debug(f"[Router] Scores: {scores} → {best_intent} ({best_score:.2f})")
    return best_intent, best_score


# ── Détection des questions d'identité ───────────────────

def _is_identity_question(text: str) -> bool:
    """Détecte 'tu es ChatGPT ?', 'c'est quoi Sëtu ?', etc."""
    t = text.lower()
    patterns = [
        r"\b(chatgpt|gpt-?\d*|openai|claude|gemini|copilot)\b",
        r"\b(tu\s+es\s+(qui|quoi|un\s+(robot|bot|ia)))\b",
        r"\b(c[' ]est\s+quoi\s+(sëtu|setu|toi))\b",
        r"\b(qui\s+(es[- ]tu|t[' ]es))\b",
    ]
    return any(re.search(p, t) for p in patterns)


# ── RouteResult ───────────────────────────────────────────

@dataclass
class RouteResult:
    intent: str
    raw_text: str
    normalized_text: str
    confiance: float
    source: str  # "cache" | "regex" | "regex_low" | "llm" | "identity"


def route(text: str) -> RouteResult:
    """Version synchrone."""
    normalized = normalize(text)
    cache_key  = normalize_for_cache(text)

    # Réponse identité directe — pas de cache, pas de LLM
    if _is_identity_question(normalized):
        return RouteResult(
            intent="out_of_scope",
            raw_text=text,
            normalized_text=normalized,
            confiance=1.0,
            source="identity"
        )

    # Cache
    cached = intent_cache.get(cache_key)
    if cached:
        return RouteResult(
            intent=cached,
            raw_text=text,
            normalized_text=normalized,
            confiance=1.0,
            source="cache"
        )

    # Fast classifier
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
    """Version async avec fallback LLM si confiance insuffisante."""
    result = route(text)

    if result.source in ("cache", "regex", "identity"):
        return result

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