"""
agent/router.py — V5.1
Intent Gateway — 4 niveaux de classification.

MIGRATIONS V5.1 depuis V5.0 :
  - RED TEAM : blacklist anti-signalement intégrée (anti_fraud.is_blacklisted_signalement)
    "je prends le 15 à liberté" ne matche plus comme signalement
  - RED TEAM : messages hybrides mieux triés (#14 "je vois le 10 mais j'attends le 15")
  - RED TEAM : "15 bi dem na" (wolof passé) détecté comme signalement négatif
  - RED TEAM : "le 15 arrive" sans localisation → question, pas signalement
  
MIGRATIONS V5.0 depuis V4.6 :
  - FIX B1 : Signalement fort extrait AUSSI les entités (ligne + arrêt)
  - FIX B3 : _is_signalement_fort() renforcé
  - FIX B4 : _is_greeting() limité aux VRAIES salutations
  - FIX B5 : _is_correction() wolof sécurisé
  - FIX A6 : _extract_ligne_from_history() exige "bus" ou "ligne"
  - VALID_LINES importé depuis config.settings
"""
import re
import logging
from dataclasses import dataclass, field

from config.settings import VALID_LINES
from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)


# ── Salutations — court-circuit immédiat, zéro LLM ───────
# FIX B4 : retiré ok/merci/parfait/super/cool/d'accord — ce sont des confirmations
_GREETING_PATTERNS = [
    r"^\s*(bonjour|bonsoir|salut|hello|hi|hey|coucou|salam|assalam)\s*[!.?]*\s*$",
    r"^\s*(bonne\s+(matinée|journée|soirée|nuit))\s*[!.?]*\s*$",
    r"^\s*(ça\s+va|ca\s+va|comment\s+(tu\s+vas|vous\s+allez|ça\s+va))\s*[!.?]*\s*$",
]

def _is_greeting(text: str) -> bool:
    t = text.strip().lower()
    return any(re.search(p, t) for p in _GREETING_PATTERNS)


# ── Négations/Corrections — court-circuit, zéro LLM ──────

# FIX B5 : mots-clés wolof positifs restreints aux VRAIS marqueurs d'intention
# Retiré : bi, la, ci, bu, ak (articles/prépositions trop fréquents)
_WOLOF_POSITIVE_CONTEXT = re.compile(
    r"\b(bëgg|dama\s+bëgg|mangi|dinaa|dama|ngi\s+dem|ñëw|jël|tëral)\b"
)

# Refus wolof explicites — priorité absolue
_WOLOF_REFUSAL = re.compile(
    r"\b(bëgguma|duma\s+ko\s+bëgg|amul\s+solo|bayil\s+lolu|bayil|wëcciku|du\s+dara|sëde\s+ko)\b"
)

_CORRECTION_PATTERNS_FR = [
    r"\b(c[' ]est\s+pas|c[' ]est\s+faux|c[' ]est\s+incorrect)\b",
    r"\b(pas\s+ma\s+(ligne|bus|arrêt|station))\b",
    r"\b(pas\s+ce\s+que\s+je\s+veux|pas\s+ça)\b",
    r"\b(oublie\s+(ça|tout)|laisse\s+tomber|laisse\s+beton)\b",
    r"\b(je\s+(ne\s+veux\s+pas|veux\s+pas)\s+(ça|aller|de\s+ça))\b",
    r"^\s*(nope|négatif|incorrect|erreur|faux)\s*[!.?]*\s*$",
]


def _is_correction(text: str) -> bool:
    t = text.strip().lower()

    # 1. Refus wolof explicites — toujours valides
    if _WOLOF_REFUSAL.search(t):
        return True

    # 2. "non" en début de message
    if re.match(r"^\s*non\b", t):
        # FIX B5 : si VRAIS marqueurs positifs wolof → pas un refus
        if _WOLOF_POSITIVE_CONTEXT.search(t):
            return False
        return True

    # 3. "nan" seul
    if re.match(r"^\s*nan\s*[!.?]*\s*$", t):
        return True

    # 4. Patterns FR
    return any(re.search(p, t) for p in _CORRECTION_PATTERNS_FR)


# ══════════════════════════════════════════════════════════════════════════════
# FIX B1+B3 : SIGNALEMENT FORT — extrait les entités ET exige ligne+localisation
# ══════════════════════════════════════════════════════════════════════════════

# Numéro de ligne valide
_LIGNE_RE = re.compile(
    r"(?:bus|ligne)\s+(\d{1,3}[A-Z]?)\b|"
    r"\b(\d{1,3}[A-Z]?)\b",
    re.IGNORECASE
)

# Arrêts connus (pour différencier localisation d'un arrêt vs "à quelle heure")
_ARRETS_CONNUS_RE = re.compile(
    r"\b(libert[eé]\s*\d?|hlm\s*\d?|gare|march[eé]|mosqu[eé]e|palais|parcelles|"
    r"m[eé]dina|plateau|sandaga|colobane|castor|ucad|yoff|pikine|thiaroye|"
    r"gu[eé]diawaye|petersen|til[eè]ne|pompiers|foire|vdn|patte\s+d[' ]oie|"
    r"point\s+e|jet\s+d[' ]eau|embarcad[eè]re|keur\s+massar|"
    r"cambérène|niary\s+tally|ouakam|almadies|grand\s+yoff|"
    r"rond\s+point|terminus|leclerc|sacr[eé]\s*c[oœ]ur|rufisque|mbao|"
    r"a[eé]roport|h[oô]pital)\b",
    re.IGNORECASE
)

# Prépositions de localisation
_LOCALISATION_RE = re.compile(
    r"\b(à|au|niveau|devant|près\s+de|derrière|ci|face\s+à|avant|en\s+face)\b",
    re.IGNORECASE
)

# Verbes d'observation / signalement (FR)
_VERBES_OBSERVATION_FR = re.compile(
    r"(?:"
    r"je\s+signal[e]?|je\s+signale\s+(?:le\s+|un\s+)?bus|"
    r"je\s+viens?\s+de\s+voir|j['']ai\s+vu|j['']aperçois?|je\s+vois|"
    r"il\s+y\s+a\s+(?:le\s+)?bus|il\s+y\s+a\s+la\s+ligne|"
    r"bus\s+(?:vient\s+de\s+)?passer|(?:le\s+)?bus\s+est\s+(?:là|ici|arrivé|devant)|"
    r"(?:le\s+)?bus\s+arrive"
    r")",
    re.IGNORECASE
)

# Verbes d'observation wolof
_VERBES_OBSERVATION_WO = re.compile(
    r"(?:"
    r"bus\s+bi\s+ngi|bi\s+ngi\s+fi|ngi\s+fi|dafa\s+ngi|"
    r"xam\s+naa|gis\s+naa|ma\s+gis|defar\s+naa"
    r")",
    re.IGNORECASE
)

# Mots qui INVALIDENT un signalement (c'est une question ou itinéraire)
_ANTI_SIGNALEMENT_RE = re.compile(
    r"\b(quelle\s+heure|combien|quand|comment\s+aller|pour\s+aller|"
    r"prendre\s+pour|à\s+quelle|est\s+où|où\s+est|ana\s+mu)\b",
    re.IGNORECASE
)

# RED TEAM : Wolof passé / négatif → pas un signalement
_WOLOF_PASSE_RE = re.compile(
    r"\b(dem\s+na|romb\s+na|jëm\s+na|dafa\s+dem|dafa\s+romb)\b",
    re.IGNORECASE
)


def _extract_ligne_from_text(text: str) -> str | None:
    """Extrait le numéro de ligne depuis le texte."""
    for m in _LIGNE_RE.finditer(text):
        num = (m.group(1) or m.group(2) or "").upper()
        if num in VALID_LINES:
            return num
    return None


def _extract_arret_from_text_router(text: str) -> str | None:
    """
    Extrait l'arrêt depuis le texte brut pour le signalement fort.
    Cherche : préposition + nom de lieu.
    """
    # Pattern : "à/niveau/devant [arrêt]"
    m = re.search(
        r"(?:à|au|niveau|devant|près\s+de|ci|face\s+à)\s+(.+?)(?:\s*[.!?,]|$)",
        text, re.IGNORECASE
    )
    if m:
        arret = m.group(1).strip()
        # Vérifier que ce n'est pas "à quelle heure", "à combien", etc.
        if not re.match(r"(quelle?|combien|quel\s+arrêt)", arret, re.IGNORECASE):
            return arret
    return None


def _is_signalement_fort(text: str) -> tuple[bool, dict]:
    """
    FIX B3 + RED TEAM : Détection prioritaire d'un signalement fort.
    Retourne (True, entities) ou (False, {}).

    Exigences renforcées :
      1. Verbe d'observation OU préposition de localisation avec arrêt connu
      2. Numéro de ligne présent
      3. PAS de mots anti-signalement (question/itinéraire)
      4. PAS de phrases blacklistées ("je prends", "j'attends", etc.)
      5. PAS de wolof au passé ("dem na" = il est parti)
    """
    t = text.strip().lower()

    # Anti-signalement : questions et itinéraires
    if _ANTI_SIGNALEMENT_RE.search(t):
        return False, {}

    # RED TEAM : blacklist "je prends", "j'attends", "si je prends"...
    from core.anti_fraud import is_blacklisted_signalement
    if is_blacklisted_signalement(t):
        return False, {}

    # RED TEAM : wolof passé ("15 bi dem na" = le 15 est parti)
    if _WOLOF_PASSE_RE.search(t):
        return False, {}

    ligne = _extract_ligne_from_text(t)
    if not ligne:
        return False, {}

    has_verbe_obs    = bool(_VERBES_OBSERVATION_FR.search(t) or _VERBES_OBSERVATION_WO.search(t))
    has_localisation = bool(_LOCALISATION_RE.search(t))
    has_arret_connu  = bool(_ARRETS_CONNUS_RE.search(t))

    # Cas 1 : verbe d'observation + ligne → signalement fort
    if has_verbe_obs:
        arret = _extract_arret_from_text_router(text) or ""
        return True, {"ligne": ligne, "origin": arret}

    # Cas 2 : ligne + localisation + arrêt connu → signalement fort
    # Ex: "Bus 8 à Liberté 6", "15 niveau Sandaga"
    if has_localisation and has_arret_connu:
        arret = _extract_arret_from_text_router(text) or ""
        return True, {"ligne": ligne, "origin": arret}

    return False, {}


# ══════════════════════════════════════════════════════════════════════════════
# SCORING RULES
# ══════════════════════════════════════════════════════════════════════════════

_SCORING_RULES: dict[str, list[tuple[str, float]]] = {

    "signalement": [
        (r"\b(signal[e]?|signaler|signalement)\b", 0.6),
        (r"\b(vu|vois|voir|aperçois?|aperçu|vient\s+de\s+passer|viens?\s+de\s+voir)\b", 0.4),
        (r"\b(là|ici|devant|niveau|arrêté|stationné|en\s+face)\b", 0.3),
        (r"\bil\s+y\s+a\b", 0.3),
        (r"\bbus\b", 0.3),
        (r"\b(\d{1,3}[A-Z]?)\b", 0.3),
        (r"\b(à|au|devant|niveau|près\s+de|derrière|avant|ci)\b", 0.4),
        (r"\b(liberté|hlm|gare|marché|mosquée|palais|parcelles|médina|plateau|"
         r"sandaga|colobane|castor|ucad|yoff|pikine|thiaroye|guédiawaye|petersen|"
         r"tilène|pompiers|foire|vdn|patte\s+d[' ]oie|point\s+e|jet\s+d[' ]eau|"
         r"embarcadère|keur\s+massar)\b", 0.2),
        (r"\b(ngi|bi\s+ngi|dafa\s+ngi|gis\s+naa|ma\s+gis|xam\s+naa|defar\s+naa)\b", 0.5),
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

    if re.search(r"\bje\s+veux\s+prendre\b", t):
        scores["itineraire"] = scores.get("itineraire", 0) * 0.2
        scores["question"]   = min(scores.get("question", 0) + 0.5, 1.0)

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
    intent:              str
    raw_text:            str
    normalized_text:     str
    confiance:           float
    source:              str
    lang:                str | None = None
    entities:            dict       = field(default_factory=dict)
    is_signalement_fort: bool       = False


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

    # 3. Court-circuit négation/correction
    if _is_correction(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="correction"
        )

    # ── FIX B1+B3 : Court-circuit SIGNALEMENT FORT avec entités ──────
    is_fort, fort_entities = _is_signalement_fort(normalized)
    if is_fort:
        logger.debug(f"[Router] Signalement fort détecté avec entités={fort_entities}")
        return RouteResult(
            intent="signalement",
            raw_text=text,
            normalized_text=normalized,
            confiance=0.97,
            source="signalement_fort",
            is_signalement_fort=True,
            entities=fort_entities,  # FIX B1 : plus jamais vide
        )

    # 4. Cache
    cached = intent_cache.get(cache_key, session_state)
    if cached:
        return RouteResult(
            intent=cached, raw_text=text,
            normalized_text=normalized, confiance=1.0, source="cache"
        )

    # 5. Scoring regex
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

    # Court-circuits totaux → jamais au LLM
    if result.source in ("greeting", "identity", "correction", "cache", "signalement_fort"):
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

            # Si le LLM dit "itineraire" mais signalement fort détecté → override
            if intent_str == "itineraire" and result.is_signalement_fort:
                logger.warning(
                    "[Router] LLM dit itineraire mais signalement fort regex → override signalement"
                )
                intent_str = "signalement"

            intent_cache.set(normalize_for_cache(text), intent_str, session_state)

            return RouteResult(
                intent=intent_str,
                raw_text=text,
                normalized_text=result.normalized_text,
                confiance=llm_data.get("confidence", 0.95),
                source="llm",
                lang=llm_data.get("lang", "fr"),
                entities=entities,
                is_signalement_fort=result.is_signalement_fort,
            )

    except Exception as e:
        logger.error(f"[Router] LLM classify failed: {e}")
        if session_context and session_context.ligne:
            if result.intent in {"question", "signalement", "abonnement", "liste_arrets"}:
                result.entities["ligne"] = session_context.ligne

    return result