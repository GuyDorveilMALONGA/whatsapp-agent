"""
core/anti_fraud.py — V7.2-test
Garde-fous anti-manipulation crowdsourcing.

MIGRATIONS V7.2-test depuis V7.1 :
  - CONFIDENCE_THRESHOLD : 0.60 → 0.35 pour période de test
    Un nouvel usager (fiabilite=0.5) + source forte donne ~0.57 → passait jamais
    Remettre 0.60 avant passage en production.

Responsabilités :
  1. Blacklist phrases → empêche les faux signalements
  2. Score de confiance signalement → threshold avant enregistrement
  3. Cohérence distance → rejette les signalements impossibles
  4. Détection patterns de spam avancé
"""
import re
import logging
from datetime import datetime, timezone, timedelta

from db import queries
from core.network import get_stop_names

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
# 1. BLACKLIST — Ces phrases NE SONT PAS des signalements
# ══════════════════════════════════════════════════════════

_NOT_SIGNALEMENT_PATTERNS = [
    r"\b(je\s+prends|je\s+vais\s+prendre|je\s+veux\s+prendre)\b",
    r"\b(j['']attends|je\s+attends)\b",
    r"\bsi\s+je\s+prends\b",
    r"\bj['']arrive\s+à\b",
    r"\bou\s+quoi\s*[?!]*$",
    r"\best\s+déjà\s+parti\b",
    r"\best\s+passé\b",
    r"\bdama\s+bëgg\s+jël\b",
    r"\bmais\s+(?:j['']attends|je\s+prends)\b",
]

_NOT_SIGNALEMENT_RE = re.compile(
    "|".join(_NOT_SIGNALEMENT_PATTERNS),
    re.IGNORECASE
)


def is_blacklisted_signalement(text: str) -> bool:
    return bool(_NOT_SIGNALEMENT_RE.search(text))


# ══════════════════════════════════════════════════════════
# 2. SCORE DE CONFIANCE SIGNALEMENT
# ══════════════════════════════════════════════════════════

# V7.2-test : abaissé à 0.35 — remettre 0.60 en production
# Calcul pour un nouvel usager (fiabilite=0.5) + source forte :
#   fiab=0.5×0.4=0.20 | src=0.95×0.3=0.285 | ent=0.9×0.2=0.18 → total=0.665
#   Avec 0.60 : passe. Mais fiabilite_score réel parfois < 0.5 → bloqué.
CONFIDENCE_THRESHOLD = 0.35  # TEST — remettre 0.60 en prod


def compute_signalement_confidence(
    phone: str,
    ligne: str,
    arret: str,
    source: str,
    has_verbe_observation: bool = False,
    has_arret_connu: bool = False,
) -> float:
    """
    Calcule un score de confiance pour un signalement.

    Composantes :
      - fiabilité usager (40%)
      - source du routing (30%)
      - qualité des entités (20%)
      - corroboration existante (10%)

    Retourne un float entre 0.0 et 1.0.
    """
    # ── Fiabilité usager (40%) ────────────────────────────
    try:
        contact = queries.get_or_create_contact(phone, "fr")
        fiabilite = contact.get("fiabilite_score", 0.5)
    except Exception:
        fiabilite = 0.5
    score_fiabilite = fiabilite * 0.4

    # ── Source du routing (30%) ───────────────────────────
    source_scores = {
        "signalement_fort": 0.95,
        "llm":              0.85,
        "regex":            0.70,
        "regex_low":        0.50,
    }
    score_source = source_scores.get(source, 0.5) * 0.3

    # ── Qualité des entités (20%) ─────────────────────────
    score_entites = 0.0
    if ligne:
        score_entites += 0.5
    if arret:
        score_entites += 0.3
    if has_verbe_observation:
        score_entites += 0.1
    if has_arret_connu:
        score_entites += 0.1
    score_entites = min(score_entites, 1.0) * 0.2

    # ── Corroboration (10%) ───────────────────────────────
    score_corroboration = 0.0
    try:
        sigs = queries.get_signalements_actifs(ligne)
        corrobore = any(
            s["position"].lower() == arret.lower()
            for s in sigs
            if s["phone"] != phone
        )
        if corrobore:
            score_corroboration = 1.0
    except Exception:
        pass
    score_corroboration *= 0.1

    total = min(score_fiabilite + score_source + score_entites + score_corroboration, 1.0)

    logger.warning(
        f"[AntiSpam] Score {phone[-4:]}: "
        f"fiab={score_fiabilite:.2f} src={score_source:.2f} "
        f"ent={score_entites:.2f} corr={score_corroboration:.2f} "
        f"TOTAL={total:.2f} THRESHOLD={CONFIDENCE_THRESHOLD}"
    )
    return total


# ══════════════════════════════════════════════════════════
# 3. COHÉRENCE DISTANCE
# ══════════════════════════════════════════════════════════

_MAX_ARRETS_PAR_2MIN = 5
_COHERENCE_WINDOW_SECONDS = 180


def check_distance_coherence(
    phone: str, ligne: str, arret_nouveau: str
) -> bool:
    try:
        derniers = queries.get_derniers_signalements_par_phone(
            phone=phone, ligne=ligne, limit=1
        )
        if not derniers:
            return True

        dernier      = derniers[0]
        dernier_arret = dernier.get("position", "")
        dernier_time  = dernier.get("timestamp", "")

        try:
            now     = datetime.now(timezone.utc)
            created = datetime.fromisoformat(dernier_time.replace("Z", "+00:00"))
            delta   = (now - created).total_seconds()
        except Exception:
            return True

        if delta > _COHERENCE_WINDOW_SECONDS:
            return True

        if dernier_arret.lower() == arret_nouveau.lower():
            return True

        stops = get_stop_names(ligne)
        if not stops:
            return True

        idx_ancien  = next(
            (i for i, n in enumerate(stops)
             if dernier_arret.lower() in n or n in dernier_arret.lower()),
            None
        )
        idx_nouveau = next(
            (i for i, n in enumerate(stops)
             if arret_nouveau.lower() in n or n in arret_nouveau.lower()),
            None
        )

        if idx_ancien is None or idx_nouveau is None:
            return True

        distance = abs(idx_nouveau - idx_ancien)
        if distance > _MAX_ARRETS_PAR_2MIN:
            logger.warning(
                f"[AntiSpam] Distance incohérente {phone[-4:]}: "
                f"{dernier_arret} → {arret_nouveau} = {distance} arrêts en {delta:.0f}s"
            )
            return False

        return True

    except Exception as e:
        logger.error(f"[AntiSpam] Erreur check distance: {e}")
        return True


# ══════════════════════════════════════════════════════════
# 4. DÉTECTION SPAM AVANCÉ
# ══════════════════════════════════════════════════════════

_SPAM_WINDOW_MINUTES = 10
_MAX_SIGNALEMENTS_PAR_FENETRE = 5


def is_spam_pattern(phone: str, ligne: str) -> bool:
    try:
        since  = (datetime.now(timezone.utc) - timedelta(minutes=_SPAM_WINDOW_MINUTES)).isoformat()
        recent = queries.get_signalements_recents_par_phone(phone, since)

        if len(recent) >= _MAX_SIGNALEMENTS_PAR_FENETRE:
            logger.warning(
                f"[AntiSpam] Spam {phone[-4:]}: "
                f"{len(recent)} signalements en {_SPAM_WINDOW_MINUTES} min"
            )
            return True

        since_5min = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        recent_5   = queries.get_signalements_recents_par_phone(phone, since_5min)
        lignes_differentes = {s.get("ligne") for s in recent_5}

        if len(lignes_differentes) >= 4:
            logger.warning(
                f"[AntiSpam] Multi-ligne spam {phone[-4:]}: "
                f"{len(lignes_differentes)} lignes en 5 min"
            )
            return True

        return False

    except Exception as e:
        logger.error(f"[AntiSpam] Erreur is_spam_pattern: {e}")
        return False