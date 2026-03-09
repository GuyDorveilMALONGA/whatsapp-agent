"""
skills/question.py — V5.2
Répond à "le bus X est où ?" et "quels sont les arrêts du bus X ?"

FIX V5.2 :
  1. handle_liste_arrets → réponse STRUCTURÉE DIRECTE depuis core.network
     Plus jamais de LLM pour lister des arrêts → impossible d'avoir "je ne connais pas"
  2. handle() → vérification ligne AVANT d'appeler generate_response()
     Si ligne introuvable dans VALID_LINES → message clair, pas de LLM
     Si ligne trouvée → LLM reçoit contexte réseau complet garanti
  3. _resolve_ligne → niveau 4 ajouté : session_context injecté par router
     (entities["ligne"] garanti si router V4.3 est utilisé)
  4. Séparation stricte : liste_arrets = réponse directe / question = LLM avec contexte
     Le LLM ne répond JAMAIS sur une ligne sans que VALID_LINES la contienne

FIX V5.1 :
  1. Source de vérité : core.network (singleton)
  2. _resolve_ligne : LLM → regex message → historique → ambiguïté 16A/16B
  3. Fuzzy matching via rag.validator
  4. handle_arret_response reçoit history explicitement
"""
import re
import logging
from datetime import datetime, timezone

from db import queries
from agent.llm_brain import generate_response
from core.context_builder import build_context
from core.network import NETWORK, VALID_LINES, get_stop_names, ambiguous_lines
from core.session_manager import get_context, set_attente_arret, reset_context
from rag.validator import normalize_arret

logger = logging.getLogger(__name__)

_MINUTES_PAR_ARRET = 3

# Nombre max d'arrêts affichés inline avant de tronquer (lisibilité WhatsApp)
_MAX_ARRETS_INLINE  = 30
_MAX_ARRETS_PREVIEW = 5


# ── Résolution de ligne ───────────────────────────────────

def _ligne_depuis_texte(text: str) -> str | None:
    match = re.search(
        r'\b(?:bus|ligne)\s*(\d{1,3}[A-Z]?|TO1|TAF\s*TAF)\b',
        text, re.IGNORECASE
    )
    if match:
        c = match.group(1).upper()
        if c in VALID_LINES:
            return c
    match2 = re.search(r'\b(\d{1,3}[A-Z]?)\b', text)
    if match2:
        c = match2.group(1).upper()
        if c in VALID_LINES:
            return c
    return None


def _ligne_depuis_historique(history: list) -> str | None:
    for msg in reversed(history or []):
        ligne = _ligne_depuis_texte(msg.get("content", ""))
        if ligne:
            return ligne
    return None


def _resolve_ligne(entities: dict, message: str,
                   history: list) -> tuple[str | None, str | None]:
    """
    Résolution en 3 niveaux + validation VALID_LINES à chaque étape.
    Retourne (ligne, ambiguity_msg).

    Niveau 1 : entities LLM  (garanti si router V4.3 actif)
    Niveau 2 : regex message brut
    Niveau 3 : historique conversation
    """
    # Niveau 1 : entities LLM (injectées par router)
    ligne = entities.get("ligne")
    if ligne:
        ligne = str(ligne).upper()
        if ligne in VALID_LINES:
            return ligne, None
        alts = ambiguous_lines(ligne)
        if alts:
            return None, f"Tu parles de *{' ou '.join(alts)}* ? Précise !"
        # Ligne inconnue : log et continuer vers N2
        logger.warning(f"[question] Ligne '{ligne}' reçue des entities mais absente de VALID_LINES")

    # Niveau 2 : regex message brut
    ligne = _ligne_depuis_texte(message)
    if ligne:
        return ligne, None

    # Niveau 3 : historique
    ligne = _ligne_depuis_historique(history)
    if ligne:
        return ligne, None

    return None, None


# ── Distance / dépassement ────────────────────────────────

def _resolve_arret(texte: str, ligne: str) -> str:
    result = normalize_arret(texte, ligne)
    if result["found"]:
        return result["arret_officiel"]
    return texte.strip()


def _calculer_distance(ligne: str, position_bus: str, arret_usager: str) -> int | None:
    stops = get_stop_names(ligne)
    if not stops:
        return None
    bus_l, usa_l = position_bus.lower(), arret_usager.lower()
    idx_bus   = next((i for i, n in enumerate(stops) if bus_l in n or n in bus_l), None)
    idx_cible = next((i for i, n in enumerate(stops) if usa_l in n or n in usa_l), None)
    if idx_bus is None or idx_cible is None:
        return None
    dist = idx_cible - idx_bus
    return dist if dist > 0 else None


def _bus_deja_passe(ligne: str, position_bus: str, arret_usager: str) -> bool:
    stops = get_stop_names(ligne)
    if not stops:
        return False
    bus_l, usa_l = position_bus.lower(), arret_usager.lower()
    idx_bus   = next((i for i, n in enumerate(stops) if bus_l in n or n in bus_l), None)
    idx_cible = next((i for i, n in enumerate(stops) if usa_l in n or n in usa_l), None)
    return (idx_bus is not None and idx_cible is not None and idx_bus > idx_cible)


# ── Flow multi-tour : réponse arrêt ──────────────────────

async def handle_arret_response(phone: str, text: str, langue: str,
                                  entities: dict, history: list) -> str:
    ctx         = get_context(phone)
    ligne       = ctx.ligne
    signalement = ctx.signalement
    reset_context(phone)

    if not ligne:
        ligne = _ligne_depuis_historique(history)

    if not ligne or not signalement:
        return (
            "Wax ma ci bus bi ak arrêt bi 🙏" if langue == "wolof"
            else "Dis-moi quel bus et à quel arrêt tu es. 🙏"
        )

    arret_brut   = entities.get("origin") or entities.get("destination") or text.strip()
    arret_usager = _resolve_arret(arret_brut, ligne)
    position_bus = signalement.get("position", "")
    deja_passe   = _bus_deja_passe(ligne, position_bus, arret_usager)

    if deja_passe:
        if langue == "wolof":
            return (
                f"😔 Bus *{ligne}* — dafa jeex ci *{arret_usager}*.\n"
                f"Bëgg nga tappaliku ? Yëgël : *Préviens-moi pour le Bus {ligne}*"
            )
        return (
            f"😔 Le Bus *{ligne}* est déjà passé à *{arret_usager}*.\n"
            f"Tu veux t'abonner ? Envoie : *Préviens-moi pour le Bus {ligne}*"
        )

    distance = _calculer_distance(ligne, position_bus, arret_usager)
    if distance is None:
        return (
            f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n"
            + ("Duma xam distance bi exact, waaye dafa jeex ci kanam. 🙏"
               if langue == "wolof"
               else "Je ne trouve pas ton arrêt exact — mais le bus avance ! 🙏")
        )

    if distance == 0:
        return f"🚌 Bus *{ligne}* est à ton arrêt *{arret_usager}* ! Cours ! 🏃"

    temps = distance * _MINUTES_PAR_ARRET
    if langue == "wolof":
        return (
            f"🚌 Bus *{ligne}* ci *{position_bus}* — "
            f"{distance} arrêt(s) ci kanam (~{temps} min). Tëral ! 🙏"
        )
    return (
        f"🚌 Bus *{ligne}* est à *{position_bus}*.\n"
        f"📍 {distance} arrêt(s) de *{arret_usager}* (~{temps} min). Prépare-toi ! 🙏"
    )


# ── Handler principal ─────────────────────────────────────

async def handle(message: str, contact: dict, langue: str,
                 history: list, entities: dict) -> str:

    ligne, ambiguity_msg = _resolve_ligne(entities, message, history)

    if ambiguity_msg:
        return ambiguity_msg

    if not ligne:
        return (
            "Numéro bus bi soxor. Wax ma : *Bus 15 est où ?* 🚌"
            if langue == "wolof"
            else "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?* 🚌"
        )

    # FIX V5.2 : vérification VALID_LINES AVANT tout appel LLM ou DB
    # Si la ligne n'est pas dans le réseau, réponse directe — jamais de LLM
    if ligne not in VALID_LINES:
        logger.error(f"[question.handle] Ligne '{ligne}' introuvable dans VALID_LINES — JSON mal chargé ?")
        return (
            f"❌ La ligne *{ligne}* n'est pas dans le réseau Dem Dikk que je connais.\n"
            f"Les lignes disponibles : envoie *liste des lignes* pour voir."
        )

    signalements = queries.get_signalements_actifs(ligne)

    if signalements:
        s = signalements[0]
        set_attente_arret(contact["phone"], ligne, s)
        try:
            now         = datetime.now(timezone.utc)
            created     = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
            minutes_ago = int((now - created).total_seconds() / 60)
            age         = f"il y a {minutes_ago} min" if minutes_ago > 0 else "à l'instant"
        except Exception:
            age = "récemment"

        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* signalé ci *{s['position']}* ({age}).\n"
                f"Fii nga nekk ? (wax ma sa arrêt)"
            )
        return (
            f"🚌 Bus *{ligne}* signalé à *{s['position']}* ({age}).\n"
            f"Tu es à quel arrêt ? Je calcule le temps d'arrivée. 📍"
        )

    # Aucun signalement — le LLM reçoit un contexte réseau complet garanti
    ctx = build_context(
        message=message, intent="question", contact=contact,
        ligne=ligne, signalements=[], history=history,
    )
    return await generate_response(ctx, langue, history)


# ── Liste des arrêts ──────────────────────────────────────

async def handle_liste_arrets(message: str, contact: dict, langue: str,
                                entities: dict, history: list) -> str:
    """
    FIX V5.2 : réponse STRUCTURÉE DIRECTE depuis core.network.
    Le LLM n'est JAMAIS appelé ici — les arrêts viennent du JSON, pas d'une génération.
    Impossible d'avoir "je ne connais pas le tracé" sur cette fonction.
    """
    ligne, ambiguity_msg = _resolve_ligne(entities, message, history)

    if ambiguity_msg:
        return ambiguity_msg

    if not ligne:
        return (
            "Numéro ligne bi soxor. Ex : *arrêts du bus 15*"
            if langue == "wolof"
            else "Quelle ligne ? Ex : *arrêts du bus 15*"
        )

    # FIX V5.2 : vérification VALID_LINES avant accès NETWORK
    if ligne not in VALID_LINES:
        logger.error(f"[question.handle_liste_arrets] Ligne '{ligne}' introuvable dans VALID_LINES")
        return (
            f"❌ La ligne *{ligne}* n'est pas dans le réseau Dem Dikk.\n"
            f"Vérifie le numéro ou envoie *liste des lignes*."
        )

    info      = NETWORK.get(ligne, {})
    stops     = info.get("stops", [])
    nom_ligne = info.get("name", "")

    if not stops:
        logger.error(f"[question.handle_liste_arrets] Ligne '{ligne}' dans VALID_LINES mais stops vide !")
        return f"❌ Aucun arrêt trouvé pour la ligne *{ligne}*. Réessaie dans un moment."

    noms = [s["nom"] for s in stops]

    # Réponse compacte si beaucoup d'arrêts (lisibilité WhatsApp)
    if len(noms) <= _MAX_ARRETS_INLINE:
        arrets_str = " → ".join(noms)
        if langue == "wolof":
            return f"🚌 Bus *{ligne}* ({nom_ligne}) :\n{arrets_str}"
        return f"🚌 *Bus {ligne}* — {nom_ligne}\nArrêts : {arrets_str}"
    else:
        # Trop d'arrêts pour tout afficher — terminus + aperçu
        debut  = " → ".join(noms[:_MAX_ARRETS_PREVIEW])
        fin    = " → ".join(noms[-_MAX_ARRETS_PREVIEW:])
        total  = len(noms)
        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* ({nom_ligne}) — {total} arrêts :\n"
                f"Départ : {debut} → ...\n"
                f"Arrivée : ... → {fin}"
            )
        return (
            f"🚌 *Bus {ligne}* — {nom_ligne} ({total} arrêts)\n"
            f"Départ : {debut} → ...\n"
            f"Arrivée : ... → {fin}"
        )