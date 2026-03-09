"""
agent/router.py — V4.4
Intent Gateway — 4 niveaux de classification.

FIX V4.4 :
  - Détection NÉGATION/CORRECTION ajoutée en court-circuit prioritaire
    (après salutations, avant tout scoring)
    Patterns : "non", "c'est pas", "oublie", "laisse tomber", "pas ma ligne",
               "je veux pas", "c'est faux", "incorrect", "erreur"
    → routé out_of_scope immédiatement, zéro LLM
    → évite que "Non le bus 5 n'est pas ma ligne" → itinéraire/question

FIX V4.3 :
  - "liste_arrets" et "question" ajoutés dans _NEEDS_ENTITIES
  - "passer" retiré des règles "question"
  - Bonus liste_arrets pour "passe par" renforcé
  - _inject_ligne_from_session() dans route() synchrone

FIX V4.2 :
  - Salutations court-circuitées avant le LLM → out_of_scope immédiat

FIX V4.1 :
  - route_async() reçoit session_context pour injection ligne multi-tour
"""
import re
import logging
from dataclasses import dataclass, field

from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)

# ── Salutations — court-circuit immédiat, zéro LLM ───────
_GREETING_PATTERNS = [
    r"^\s*(bonjour|bonsoir|salut|hello|hi|hey|coucou|salam|assalam|waw|waaw|waoh)\s*[!.?]*\s*$",
    r"^\s*(bonne\s+(matinée|journée|soirée|nuit))\s*[!.?]*\s*$",
    r"^\s*(ça\s+va|ca\s+va|comment\s+(tu\s+vas|vous\s+allez|ça\s+va))\s*[!.?]*\s*$",
    r"^\s*(merci|thank\s*you|thanks|ok|okay|oublie|laisse\s+tomber|d['']accord|parfait|super|cool)\s*[!.?]*\s*$",
]

def _is_greeting(text: str) -> bool:
    t = text.strip().lower()
    return any(re.search(p, t) for p in _GREETING_PATTERNS)


# ── Négations/Corrections — court-circuit, zéro LLM ──────
# Si l'usager nie ou corrige → out_of_scope immédiatement
# Priorité absolue sur tout scoring (bus X présent ou non)
_CORRECTION_PATTERNS = [
    r"^\s*non\b",                                    # "Non le bus 5..."
    r"\b(c[' ]est\s+pas|c[' ]est\s+faux|c[' ]est\s+incorrect)\b",
    r"\b(pas\s+ma\s+(ligne|bus|arrêt|station))\b",
    r"\b(pas\s+ce\s+que\s+je\s+veux|pas\s+ça)\b",
    r"\b(oublie\s+(ça|tout)|laisse\s+tomber|laisse\s+beton)\b",
    r"\b(je\s+(ne\s+veux\s+pas|veux\s+pas)\s+(ça|aller|de\s+ça))\b",
    r"^\s*(nan|nope|négatif|incorrect|erreur|faux)\s*[!.?]*\s*$",
]

def _is_correction(text: str) -> bool:
    t = text.strip().lower()
    return any(re.search(p, t) for p in _CORRECTION_PATTERNS)


_SCORING_RULES: dict[str, list[tuple[str, float]]] = {

    "signalement": [
        (r"\bbus\b", 0.3),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.3),
        (r"\b(à|au|devant|niveau|près de|derrière|avant|ci)\b", 0.4),
        (r"\b(liberté|hlm|gare|marché|mosquée|palais|parcelles)\b", 0.2),
        (r"\b(vu|vois|voir|vient|passé|là|ici)\b", 0.2),
    ],

    "question": [
        (r"\b(où|ou|woon|ngelaw|est\s+où)\b", 0.5),
        (r"\b(quand|combien|minutes?|heures?)\b", 0.4),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.2),
        (r"\b(bus|ligne)\b", 0.2),
        (r"\?", 0.2),
        (r"\b(arriver|venir|attendre)\b", 0.3),
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
        (r"\b(passe\s+par|par\s+où|passe\s+où|où\s+passe)\b", 0.7),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.2),
        (r"\b(trajet|parcours|route)\b", 0.3),
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

_NEEDS_ENTITIES = {"signalement", "itineraire", "abonnement", "liste_arrets", "question"}

_NO_HISTORY_INTENTS = {"out_of_scope", "abandon", "escalade"}


def _apply_penalties(text: str, scores: dict[str, float]) -> dict[str, float]:
    t        = text.lower()
    je_suis  = re.search(r"\bje\s+(suis|me\s+trouve)\s+(à|au|ici|là)\b", t)
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
    t      = text.lower()
    scores: dict[str, float] = {}
    for intent, rules in _SCORING_RULES.items():
        score = 0.0
        for pattern, weight in rules:
            if re.search(pattern, t):
                score += weight
        scores[intent] = min(score, 1.0)
    scores      = _apply_penalties(t, scores)
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
    intent:          str
    raw_text:        str
    normalized_text: str
    confiance:       float
    source:          str
    lang:            str | None = None
    entities:        dict       = field(default_factory=dict)


def route(text: str, session_state: str | None = None) -> RouteResult:
    normalized = normalize(text)
    cache_key  = normalize_for_cache(text)

    # 1. Court-circuit salutation
    if _is_greeting(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="greeting"
        )

    # 2. Court-circuit identité
    if _is_identity_question(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="identity"
        )

    # 3. Court-circuit négation/correction — PRIORITÉ ABSOLUE
    # "Non le bus 5 n'est pas ma ligne" → out_of_scope, zéro LLM
    if _is_correction(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="correction"
        )

    cached = intent_cache.get(cache_key, session_state)
    if cached:
        return RouteResult(
            intent=cached, raw_text=text,
            normalized_text=normalized, confiance=1.0, source="cache"
        )

    intent, score = _fast_classify(normalized)

    if score >= _SCORE_THRESHOLD and intent not in _NEEDS_ENTITIES:
        intent_cache.set(cache_key, intent, session_state)
        return RouteResult(
            intent=intent, raw_text=text,
            normalized_text=normalized, confiance=score, source="regex"
        )

    return RouteResult(
        intent=intent, raw_text=text,
        normalized_text=normalized, confiance=score, source="regex_low"
    )


async def route_async(
    text: str,
    history: list | None = None,
    session_state: str | None = None,
    session_context=None,
) -> RouteResult:
    result = route(text, session_state)

    # Court-circuit total : salutation, identité, correction, cache → jamais au LLM
    if result.source in ("greeting", "identity", "correction", "cache"):
        return result

    if result.source == "regex" and result.intent not in _NEEDS_ENTITIES:
        return result

    logger.info(
        f"[Router] Escalade LLM "
        f"(source={result.source} | intent={result.intent} | score={result.confiance:.2f})"
    )

    try:
        from agent.llm_brain import classify_intent, _VALID_INTENTS

        history_for_llm = None
        if result.intent not in _NO_HISTORY_INTENTS:
            history_for_llm = history

        llm_data = await classify_intent(
            text=result.normalized_text,
            history=history_for_llm
        )

        if llm_data and isinstance(llm_data, dict):
            intent_str = llm_data.get("intent", "out_of_scope")

            if intent_str not in _VALID_INTENTS:
                logger.warning(f"[Router] Intent LLM inconnu: {intent_str} → fallback regex")
                return result

            entities = llm_data.get("entities") or {}

            if not entities.get("ligne") and session_context and session_context.ligne:
                if intent_str in {"question", "signalement", "abonnement", "liste_arrets"}:
                    entities = dict(entities)
                    entities["ligne"] = session_context.ligne
                    logger.debug(
                        f"[Router] Ligne injectée depuis session: {session_context.ligne}"
                    )

            intent_cache.set(normalize_for_cache(text), intent_str, session_state)

            return RouteResult(
                intent=intent_str,
                raw_text=text,
                normalized_text=result.normalized_text,
                confiance=llm_data.get("confidence", 0.95),
                source="llm",
                lang=llm_data.get("lang", "fr"),
                entities=entities,
            )

    except Exception as e:
        logger.error(f"[Router] LLM classify failed: {e}")
        if session_context and session_context.ligne:
            if result.intent in {"question", "signalement", "abonnement", "liste_arrets"}:
                result.entities["ligne"] = session_context.ligne

    return result