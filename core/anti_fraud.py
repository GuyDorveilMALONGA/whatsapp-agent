"""
core/anti_fraud.py — V7.1 (NOUVEAU)
Garde-fous anti-manipulation crowdsourcing.

Responsabilités :
  1. Blacklist phrases → empêche les faux signalements
  2. Score de confiance signalement → threshold avant enregistrement
  3. Cohérence distance → rejette les signalements impossibles
  4. Détection patterns de spam avancé

Source : Red Team 50 attaques (document interne)
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

# Attaques #11, #13, #15, #20 du red team
_NOT_SIGNALEMENT_PATTERNS = [
    # "je prends le bus" = intention, pas observation
    r"\b(je\s+prends|je\s+vais\s+prendre|je\s+veux\s+prendre)\b",
    # "j'attends le bus" = attente, pas observation
    r"\b(j['']attends|je\s+attends)\b",
    # "si je prends" = hypothèse
    r"\bsi\s+je\s+prends\b",
    # "j'arrive à" = question itinéraire
    r"\bj['']arrive\s+à\b",
    # Question déguisée : "est là ou quoi", "est à sandaga ou quoi"
    r"\bou\s+quoi\s*[?!]*$",
    # Passé certain : "est déjà parti", "est passé"
    r"\best\s+déjà\s+parti\b",
    r"\best\s+passé\b",
    # Wolof : "je vais prendre" = dama bëgg jël
    r"\bdama\s+bëgg\s+jël\b",
    # "mais j'attends/je prends" = pas signalement pour la ligne mentionnée après
    r"\bmais\s+(?:j['']attends|je\s+prends)\b",
]

_NOT_SIGNALEMENT_RE = re.compile(
    "|".join(_NOT_SIGNALEMENT_PATTERNS),
    re.IGNORECASE
)


def is_blacklisted_signalement(text: str) -> bool:
    """
    Retourne True si le message contient une expression
    qui indique que ce n'est PAS un signalement réel.
    
    Couvre les attaques red team :
      #11 "je prends le 15 à liberté 5"
      #13 "si je prends le 15 à sandaga j'arrive à UCAD ?"
      #15 "le 15 est là mais je prends le 8"
      #20 "je vais prendre le 15 à sandaga"
    """
    return bool(_NOT_SIGNALEMENT_RE.search(text))


# ══════════════════════════════════════════════════════════
# 2. SCORE DE CONFIANCE SIGNALEMENT
# ══════════════════════════════════════════════════════════

# Seuil minimum pour enregistrer un signalement
CONFIDENCE_THRESHOLD = 0.60

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
        "signalement_fort": 0.95,  # regex fort = très fiable
        "llm":              0.85,  # LLM = fiable
        "regex":            0.70,  # regex seul = moyen
        "regex_low":        0.50,  # regex faible = risqué
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

    total = score_fiabilite + score_source + score_entites + score_corroboration
    total = min(total, 1.0)

    logger.debug(
        f"[AntiSpam] Score signalement {phone[-4:]}: "
        f"fiab={score_fiabilite:.2f} src={score_source:.2f} "
        f"ent={score_entites:.2f} corr={score_corroboration:.2f} "
        f"TOTAL={total:.2f}"
    )
    return total


# ══════════════════════════════════════════════════════════
# 3. COHÉRENCE DISTANCE — Rejette les signalements impossibles
# ══════════════════════════════════════════════════════════

# Un bus fait au maximum ~15 arrêts en 2 minutes (impossible en réalité)
_MAX_ARRETS_PAR_2MIN = 5
_COHERENCE_WINDOW_SECONDS = 180  # 3 minutes


def check_distance_coherence(
    phone: str, ligne: str, arret_nouveau: str
) -> bool:
    """
    Vérifie que le signalement est géographiquement cohérent
    avec le signalement précédent du même usager sur la même ligne.
    
    Retourne True si cohérent (ou si pas de signalement précédent).
    Retourne False si la distance est impossible (spam bus fantôme).
    
    Couvre l'attaque red team #21-#24 : "bus fantôme progressif"
    (bus 15 sandaga → bus 15 UCAD en 2 min = impossible)
    """
    try:
        # Chercher le dernier signalement de cet usager sur cette ligne
        derniers = queries.get_derniers_signalements_par_phone(
            phone=phone, ligne=ligne, limit=1
        )
        if not derniers:
            return True  # Pas de signalement précédent → OK

        dernier = derniers[0]
        dernier_arret = dernier.get("position", "")
        dernier_time  = dernier.get("timestamp", "")

        # Vérifier le délai
        try:
            now     = datetime.now(timezone.utc)
            created = datetime.fromisoformat(dernier_time.replace("Z", "+00:00"))
            delta   = (now - created).total_seconds()
        except Exception:
            return True  # Impossible de parser → on laisse passer

        if delta > _COHERENCE_WINDOW_SECONDS:
            return True  # Plus de 3 min → OK, le bus a pu bouger

        # Même arrêt → c'est un doublon, pas un problème de distance
        if dernier_arret.lower() == arret_nouveau.lower():
            return True

        # Calculer la distance en arrêts
        stops = get_stop_names(ligne)
        if not stops:
            return True  # Pas de données GPS → on laisse passer

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
            return True  # Arrêt non trouvé → on laisse passer

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
        return True  # Erreur → fail open


# ══════════════════════════════════════════════════════════
# 4. DÉTECTION SPAM AVANCÉ
# ══════════════════════════════════════════════════════════

_SPAM_WINDOW_MINUTES = 10
_MAX_SIGNALEMENTS_PAR_FENETRE = 5


def is_spam_pattern(phone: str, ligne: str) -> bool:
    """
    Détecte les patterns de spam avancé :
      - Plus de 5 signalements en 10 minutes (même usager)
      - Signalements sur 4+ lignes différentes en 5 minutes
    
    Couvre attaque red team #25 : multi-ligne spam
    et #30 : spam leaderboard.
    """
    try:
        # Check 1 : trop de signalements par cet usager (toutes lignes)
        since = (datetime.now(timezone.utc) - timedelta(minutes=_SPAM_WINDOW_MINUTES)).isoformat()
        recent = queries.get_signalements_recents_par_phone(phone, since)

        if len(recent) >= _MAX_SIGNALEMENTS_PAR_FENETRE:
            logger.warning(
                f"[AntiSpam] Spam détecté {phone[-4:]}: "
                f"{len(recent)} signalements en {_SPAM_WINDOW_MINUTES} min"
            )
            return True

        # Check 2 : trop de lignes différentes en peu de temps
        since_5min = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        recent_5 = queries.get_signalements_recents_par_phone(phone, since_5min)
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
        return False  # Fail open
