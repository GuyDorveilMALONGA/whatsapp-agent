"""
agent/router.py — V5.2
Intent Gateway — 4 niveaux de classification.

MIGRATIONS V5.2 depuis V5.1 :
  - FIX B1-TG : Cas 3 signalement fort — arrêt connu SANS préposition
    "Bus 15 liberté 5", "15 Sandaga", "Bus DDD Petersen" → signalement ✅
  - FIX B4 : _extract_arret_connu() robuste — fallback sur match regex si after_ligne vide
  - FIX B8 : _is_enrichissement_qualitatif() capture TOUTES les qualités d'un message multi-qualité
    "bondé et en retard" → qualites = ["bondé", "en retard"] (retourné pour enrichissement multiple)

MIGRATIONS V5.1 depuis V5.0 :
  - RED TEAM : blacklist anti-signalement intégrée (anti_fraud.is_blacklisted_signalement)
  - RED TEAM : messages hybrides mieux triés
  - RED TEAM : "15 bi dem na" (wolof passé) détecté comme signalement négatif
  - RED TEAM : "le 15 arrive" sans localisation → question, pas signalement
"""
import re
import logging
from dataclasses import dataclass, field

from config.settings import VALID_LINES
from agent.normalizer import normalize, normalize_for_cache
from agent import intent_cache

logger = logging.getLogger(__name__)


# ── Salutations — court-circuit immédiat, zéro LLM ───────
_GREETING_PATTERNS = [
    r"^\s*(bonjour|bonsoir|salut|hello|hi|hey|coucou|salam|assalam)\s*[!.?]*\s*$",
    r"^\s*(bonne\s+(matinée|journée|soirée|nuit))\s*[!.?]*\s*$",
    r"^\s*(ça\s+va|ca\s+va|comment\s+(tu\s+vas|vous\s+allez|ça\s+va))\s*[!.?]*\s*$",
]

def _is_greeting(text: str) -> bool:
    t = text.strip().lower()
    return any(re.search(p, t) for p in _GREETING_PATTERNS)


# ── Négations/Corrections ─────────────────────────────────
_WOLOF_POSITIVE_CONTEXT = re.compile(
    r"\b(bëgg|dama\s+bëgg|mangi|dinaa|dama|ngi\s+dem|ñëw|jël|tëral)\b"
)
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
    if _WOLOF_REFUSAL.search(t):
        return True
    if re.match(r"^\s*non\b", t):
        if _WOLOF_POSITIVE_CONTEXT.search(t):
            return False
        return True
    if re.match(r"^\s*nan\s*[!.?]*\s*$", t):
        return True
    return any(re.search(p, t) for p in _CORRECTION_PATTERNS_FR)


# ══════════════════════════════════════════════════════════════════════════════
# SIGNALEMENT FORT — détection + extraction entités
# ══════════════════════════════════════════════════════════════════════════════

_LIGNE_RE = re.compile(
    r"(?:bus|ligne)\s+(\d{1,3}[A-Z]?)\b|"
    r"\b(\d{1,3}[A-Z]?)\b",
    re.IGNORECASE
)

_ARRETS_CONNUS_RE = re.compile(
    r"\b(libert[eé]\s*\d?|hlm\s*\d?|gare|march[eé]|mosqu[eé]e|palais|parcelles|"
    r"m[eé]dina|plateau|sandaga|colobane|castor|ucad|yoff|pikine|thiaroye|"
    r"gu[eé]diawaye|petersen|til[eè]ne|pompiers|foire|vdn|patte\s+d[' ]oie|"
    r"point\s+e|jet\s+d[' ]eau|embarcad[eè]re|keur\s+massar|"
    r"camb[eé]r[eè]ne|niary\s+tally|ouakam|almadies|grand\s+yoff|"
    r"rond\s+point|terminus|leclerc|sacr[eé]\s*c[oœ]ur|rufisque|mbao|"
    r"a[eé]roport|h[oô]pital)\b",
    re.IGNORECASE
)

_LOCALISATION_RE = re.compile(
    r"\b(à|au|niveau|devant|près\s+de|derrière|ci|face\s+à|avant|en\s+face)\b",
    re.IGNORECASE
)

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

_VERBES_OBSERVATION_WO = re.compile(
    r"(?:"
    r"bus\s+bi\s+ngi|bi\s+ngi\s+fi|ngi\s+fi|dafa\s+ngi|"
    r"xam\s+naa|gis\s+naa|ma\s+gis|defar\s+naa"
    r")",
    re.IGNORECASE
)

_ANTI_SIGNALEMENT_RE = re.compile(
    r"\b(quelle\s+heure|combien|quand|comment\s+aller|pour\s+aller|"
    r"prendre\s+pour|à\s+quelle|est\s+où|où\s+est|ana\s+mu)\b",
    re.IGNORECASE
)

_WOLOF_PASSE_RE = re.compile(
    r"\b(dem\s+na|romb\s+na|jëm\s+na|dafa\s+dem|dafa\s+romb)\b",
    re.IGNORECASE
)


def _extract_ligne_from_text(text: str) -> str | None:
    for m in _LIGNE_RE.finditer(text):
        num = (m.group(1) or m.group(2) or "").upper()
        if num in VALID_LINES:
            return num
    return None


def _extract_arret_from_text_router(text: str) -> str | None:
    """Extrait l'arrêt après une préposition."""
    m = re.search(
        r"(?:à|au|niveau|devant|près\s+de|ci|face\s+à)\s+(.+?)(?:\s*[.!?,]|$)",
        text, re.IGNORECASE
    )
    if m:
        arret = m.group(1).strip()
        if not re.match(r"(quelle?|combien|quel\s+arrêt)", arret, re.IGNORECASE):
            return arret
    return None


def _extract_arret_connu(text: str) -> str | None:
    """
    FIX B4 : Extrait l'arrêt connu depuis le texte, SANS préposition requise.
    Stratégie : tout ce qui suit le numéro de ligne dans le texte.
    Fallback : le match regex directement.
    """
    # Essaie d'abord ce qui suit "bus NNN" ou "ligne NNN"
    after_match = re.search(
        r"(?:bus|ligne)\s*\d{1,3}[A-Z]?\s+(.+?)(?:\s*[.!?,]|$)",
        text, re.IGNORECASE
    )
    if after_match:
        candidate = after_match.group(1).strip()
        if candidate and len(candidate) >= 2:
            return candidate

    # Fallback : retourne le nom d'arrêt connu directement
    m = _ARRETS_CONNUS_RE.search(text)
    if m:
        return m.group(0).strip()

    return None


def _is_signalement_fort(text: str) -> tuple[bool, dict]:
    """
    V5.2 : Détection prioritaire d'un signalement fort.
    Retourne (True, entities) ou (False, {}).

    Cas 1 : verbe d'observation + ligne
    Cas 2 : ligne + préposition + arrêt connu
    Cas 3 (NEW) : "bus NNN [arrêt connu]" sans préposition — pattern le plus fréquent sur mobile
    """
    t = text.strip().lower()

    # Anti-signalement : questions et itinéraires
    if _ANTI_SIGNALEMENT_RE.search(t):
        return False, {}

    # Blacklist "je prends", "j'attends", etc.
    from core.anti_fraud import is_blacklisted_signalement
    if is_blacklisted_signalement(t):
        return False, {}

    # Wolof passé ("15 bi dem na" = le 15 est parti)
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
        arret = _extract_arret_from_text_router(text) or _extract_arret_connu(text) or ""
        return True, {"ligne": ligne, "origin": arret}

    # Cas 2 : ligne + préposition + arrêt connu
    if has_localisation and has_arret_connu:
        arret = _extract_arret_from_text_router(text) or _extract_arret_connu(text) or ""
        return True, {"ligne": ligne, "origin": arret}

    # Cas 3 (FIX B1-TG) : "Bus 15 liberté 5", "Bus DDD Sandaga", "15 Petersen"
    # Pattern minimal mais non ambigu : mot "bus" ou "ligne" + numéro valide + arrêt connu
    # Pas de verbe de question, pas de destination (pas d'itinéraire implicite)
    if has_arret_connu and re.search(r"\b(bus|ligne)\b", text, re.IGNORECASE):
        arret = _extract_arret_connu(text) or ""
        if arret:
            logger.debug(f"[Router] Signalement fort Cas 3 — ligne={ligne} arret={arret}")
            return True, {"ligne": ligne, "origin": arret}

    return False, {}


# ══════════════════════════════════════════════════════════════════════════════
# FIX B8 : Enrichissement qualitatif multi-qualités
# ══════════════════════════════════════════════════════════════════════════════

# Mapping qualité → pattern (ordre : du plus spécifique au plus général)
_QUALITE_PATTERNS: list[tuple[str, str]] = [
    ("déjà parti",        r"\b(vient\s+de\s+partir|vient\s+de\s+passer|déjà\s+parti|dem\s+na)\b"),
    ("repart maintenant", r"\b(il\s+repart|repart\s+maintenant)\b"),
    ("bondé",             r"\b(bond[eé]|plein|blindé|bourr[eé])\b"),
    ("vide",              r"\b(vide|personne\s+dedans|d[eé]sert)\b"),
    ("en retard",         r"\ben\s+retard\b"),
]

def extract_qualites(text: str) -> list[str]:
    """
    FIX B8 : Retourne TOUTES les qualités présentes dans le message.
    "bondé et en retard" → ["bondé", "en retard"]
    """
    t = text.strip().lower()
    found = []
    for qualite, pattern in _QUALITE_PATTERNS:
        if re.search(pattern, t):
            found.append(qualite)
    return found


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
_NEEDS_ENTITIES  = {"signalement", "itineraire", "abonnement", "liste_arrets", "question"}
_NO_HISTORY_INTENTS = {"out_of_scope", "abandon", "escalade"}


def _apply_penalties(text: str, scores: dict[str, float]) -> dict[str, float]:
    t       = text.lower()
    je_suis = re.search(r"\bje\s+(suis|me\s+trouve)\s+(à|au|ici|là)\b", t)
    has_bus = re.search(r"\bbus\b", t)

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

    if _is_greeting(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="greeting"
        )

    if _is_identity_question(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="identity"
        )

    if _is_correction(normalized):
        return RouteResult(
            intent="out_of_scope", raw_text=text,
            normalized_text=normalized, confiance=1.0, source="correction"
        )

    # Court-circuit SIGNALEMENT FORT
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
            entities=fort_entities,
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

            # Injection ligne depuis session uniquement si pas déjà présente
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