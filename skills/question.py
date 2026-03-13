"""
skills/question.py — V5.4
Cold start → core.frequencies.format_service() au lieu de generate_response() LLM.

MIGRATION V5.4 depuis V5.3 :
  - FIX : handle_liste_arrets utilisait s["nom"] — champ v3.
    Depuis v4, le champ est s["name"]. Corrigé.
  - Aucun autre changement logique.
"""
import re
import logging
from datetime import datetime, timezone

from db import queries
from core.network import NETWORK, VALID_LINES, get_stop_names, ambiguous_lines
from core.session_manager import get_context, set_attente_arret, reset_context
from core.frequencies import format_service
from rag.validator import normalize_arret

logger = logging.getLogger(__name__)

_MINUTES_PAR_ARRET = 3
_MAX_ARRETS_INLINE  = 30
_MAX_ARRETS_PREVIEW = 5


def _ligne_depuis_texte(text: str) -> str | None:
    match = re.search(r'\b(?:bus|ligne)\s*(\d{1,3}[A-Z]?|TO1|TAF\s*TAF)\b', text, re.IGNORECASE)
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


def _resolve_ligne(entities: dict, message: str, history: list) -> tuple[str | None, str | None]:
    ligne = entities.get("ligne")
    if ligne:
        ligne = str(ligne).upper()
        if ligne in VALID_LINES:
            return ligne, None
        alts = ambiguous_lines(ligne)
        if alts:
            return None, f"Tu parles de *{' ou '.join(alts)}* ? Précise !"
        logger.warning(f"[question] Ligne '{ligne}' absente de VALID_LINES")
    ligne = _ligne_depuis_texte(message)
    if ligne:
        return ligne, None
    ligne = _ligne_depuis_historique(history)
    if ligne:
        return ligne, None
    return None, None


def _resolve_arret(texte: str, ligne: str) -> str:
    result = normalize_arret(texte, ligne)
    return result["arret_officiel"] if result["found"] else texte.strip()


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
    return idx_bus is not None and idx_cible is not None and idx_bus > idx_cible


async def handle_arret_response(phone: str, text: str, langue: str,
                                  entities: dict, history: list) -> str:
    ctx         = get_context(phone)
    ligne       = ctx.ligne
    signalement = ctx.signalement
    reset_context(phone)
    if not ligne:
        ligne = _ligne_depuis_historique(history)
    if not ligne or not signalement:
        return "Wax ma ci bus bi ak arrêt bi 🙏" if langue == "wolof" else "Dis-moi quel bus et à quel arrêt tu es. 🙏"
    arret_brut   = entities.get("origin") or entities.get("destination") or text.strip()
    arret_usager = _resolve_arret(arret_brut, ligne)
    position_bus = signalement.get("position", "")
    if _bus_deja_passe(ligne, position_bus, arret_usager):
        if langue == "wolof":
            return f"😔 Bus *{ligne}* — dafa jeex ci *{arret_usager}*.\nBëgg nga tappaliku ? Yëgël : *Préviens-moi pour le Bus {ligne}*"
        return f"😔 Le Bus *{ligne}* est déjà passé à *{arret_usager}*.\nTu veux t'abonner ? Envoie : *Préviens-moi pour le Bus {ligne}*"
    distance = _calculer_distance(ligne, position_bus, arret_usager)
    if distance is None:
        return (f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n" +
                ("Duma xam distance bi exact, waaye dafa jeex ci kanam. 🙏" if langue == "wolof"
                 else "Je ne trouve pas ton arrêt exact — mais le bus avance ! 🙏"))
    if distance == 0:
        return f"🚌 Bus *{ligne}* est à ton arrêt *{arret_usager}* ! Cours ! 🏃"
    temps = distance * _MINUTES_PAR_ARRET
    if langue == "wolof":
        return f"🚌 Bus *{ligne}* ci *{position_bus}* — {distance} arrêt(s) ci kanam (~{temps} min). Tëral ! 🙏"
    return f"🚌 Bus *{ligne}* est à *{position_bus}*.\n📍 {distance} arrêt(s) de *{arret_usager}* (~{temps} min). Prépare-toi ! 🙏"


async def handle(message: str, contact: dict, langue: str,
                 history: list, entities: dict) -> str:
    ligne, ambiguity_msg = _resolve_ligne(entities, message, history)
    if ambiguity_msg:
        return ambiguity_msg
    if not ligne:
        return ("Numéro bus bi soxor. Wax ma : *Bus 15 est où ?* 🚌" if langue == "wolof"
                else "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?* 🚌")
    if ligne not in VALID_LINES:
        logger.error(f"[question.handle] Ligne '{ligne}' introuvable dans VALID_LINES")
        return (f"❌ La ligne *{ligne}* n'est pas dans le réseau Dem Dikk.\n"
                f"Envoie *liste des lignes* pour voir les lignes disponibles.")

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
            return f"🚌 Bus *{ligne}* signalé ci *{s['position']}* ({age}).\nFii nga nekk ? (wax ma sa arrêt)"
        return f"🚌 Bus *{ligne}* signalé à *{s['position']}* ({age}).\nTu es à quel arrêt ? Je calcule le temps d'arrivée. 📍"

    # ── Cold start : fréquences estimées ─────────────────
    dernier_age = None
    try:
        derniers = queries.get_derniers_signalements(ligne, limit=1)
        if derniers:
            now     = datetime.now(timezone.utc)
            created = datetime.fromisoformat(derniers[0]["timestamp"].replace("Z", "+00:00"))
            dernier_age = int((now - created).total_seconds() / 60)
    except Exception as e:
        logger.warning(f"[question.handle] get_derniers_signalements erreur: {e}")
    return format_service(ligne, langue, signalement_age_min=dernier_age)


async def handle_liste_arrets(message: str, contact: dict, langue: str,
                                entities: dict, history: list) -> str:
    ligne, ambiguity_msg = _resolve_ligne(entities, message, history)
    if ambiguity_msg:
        return ambiguity_msg
    if not ligne:
        return ("Numéro ligne bi soxor. Ex : *arrêts du bus 15*" if langue == "wolof"
                else "Quelle ligne ? Ex : *arrêts du bus 15*")
    if ligne not in VALID_LINES:
        logger.error(f"[question.handle_liste_arrets] Ligne '{ligne}' introuvable")
        return (f"❌ La ligne *{ligne}* n'est pas dans le réseau Dem Dikk.\n"
                f"Vérifie le numéro ou envoie *liste des lignes*.")
    info      = NETWORK.get(ligne, {})
    stops     = info.get("stops", [])
    nom_ligne = info.get("name", "")
    if not stops:
        return f"❌ Aucun arrêt trouvé pour la ligne *{ligne}*. Réessaie dans un moment."

    # FIX V5.4 : champ "name" (v4+) au lieu de "nom" (v3)
    noms = [s["name"] for s in stops if s.get("name")]

    if len(noms) <= _MAX_ARRETS_INLINE:
        arrets_str = " → ".join(noms)
        if langue == "wolof":
            return f"🚌 Bus *{ligne}* ({nom_ligne}) :\n{arrets_str}"
        return f"🚌 *Bus {ligne}* — {nom_ligne}\nArrêts : {arrets_str}"
    debut = " → ".join(noms[:_MAX_ARRETS_PREVIEW])
    fin   = " → ".join(noms[-_MAX_ARRETS_PREVIEW:])
    total = len(noms)
    if langue == "wolof":
        return (f"🚌 Bus *{ligne}* ({nom_ligne}) — {total} arrêts :\n"
                f"Départ : {debut} → ...\nArrivée : ... → {fin}")
    return (f"🚌 *Bus {ligne}* — {nom_ligne} ({total} arrêts)\n"
            f"Départ : {debut} → ...\nArrivée : ... → {fin}")