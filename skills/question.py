"""
skills/question.py — V5
Répond à "le bus X est où ?" et "quels sont les arrêts du bus X ?"

FIX DÉFINITIF :
  1. Chargement JSON lazy + validation au démarrage
  2. entities enrichies depuis l'historique si vides (fallback multi-tour)
  3. handle_liste_arrets : ligne depuis entities OU historique
"""
import json
import logging
from datetime import datetime, timezone
from db import queries
from agent.llm_brain import generate_response
from core.context_builder import build_context
from core.session_manager import (
    get_context, set_attente_arret, reset_context
)

logger = logging.getLogger(__name__)

_MINUTES_PAR_ARRET = 3

# ── Chargement source de vérité ───────────────────────────
_NETWORK: dict    = {}
_VALID_LINES: set = set()

def _load_json():
    global _NETWORK, _VALID_LINES
    try:
        with open("dem_dikk_lines_gps_final.json", "r", encoding="utf-8") as f:
            _RAW = json.load(f)
        for _lines in _RAW.get("categories", {}).values():
            for _line in _lines:
                num = str(_line.get("number", "")).upper()
                if num:
                    _NETWORK[num] = _line
                    _VALID_LINES.add(num)
        logger.info(f"[Question] JSON chargé : {len(_VALID_LINES)} lignes")
    except Exception as e:
        logger.error(f"[Question] Erreur critique chargement JSON : {e}")

_load_json()


# ── Helpers ───────────────────────────────────────────────

def _get_stops(ligne: str) -> list[str]:
    line_data = _NETWORK.get(str(ligne).upper(), {})
    return [s["nom"].lower() for s in line_data.get("stops", [])]


def _calculer_distance(ligne: str, position_bus: str, arret_usager: str) -> int | None:
    stops = _get_stops(ligne)
    if not stops:
        return None
    bus_lower    = position_bus.lower()
    usager_lower = arret_usager.lower()
    idx_bus   = next((i for i, n in enumerate(stops) if bus_lower in n or n in bus_lower), None)
    idx_cible = next((i for i, n in enumerate(stops) if usager_lower in n or n in usager_lower), None)
    if idx_bus is None or idx_cible is None:
        return None
    dist = idx_cible - idx_bus
    return dist if dist > 0 else None


def _bus_deja_passe(ligne: str, position_bus: str, arret_usager: str) -> bool:
    stops = _get_stops(ligne)
    if not stops:
        return False
    bus_lower    = position_bus.lower()
    usager_lower = arret_usager.lower()
    idx_bus   = next((i for i, n in enumerate(stops) if bus_lower in n or n in bus_lower), None)
    idx_cible = next((i for i, n in enumerate(stops) if usager_lower in n or n in usager_lower), None)
    if idx_bus is not None and idx_cible is not None:
        return idx_bus > idx_cible
    return False


def _ligne_depuis_historique(history: list) -> str | None:
    """
    Cherche la dernière ligne mentionnée dans l'historique.
    Permet "et pour la ligne 8 ?" après avoir parlé du 232.
    """
    import re
    for msg in reversed(history or []):
        content = msg.get("content", "")
        match = re.search(
            r'\b(?:bus|ligne)\s*(\d{1,3}[A-Z]?|TO1|TAF\s*TAF)\b',
            content, re.IGNORECASE
        )
        if match:
            candidate = match.group(1).upper()
            if candidate in _VALID_LINES:
                return candidate
    return None


def _ligne_depuis_message(text: str) -> str | None:
    """
    Extraction directe depuis le message brut.
    Utilisé quand les entities LLM sont vides.
    """
    import re
    match = re.search(
        r'\b(?:bus|ligne)\s*(\d{1,3}[A-Z]?|TO1|TAF\s*TAF)\b',
        text, re.IGNORECASE
    )
    if match:
        candidate = match.group(1).upper()
        if candidate in _VALID_LINES:
            return candidate
    # Essai numéro seul (ex: "et le 8 ?")
    match2 = re.search(r'\b(\d{1,3}[A-Z]?)\b', text)
    if match2:
        candidate = match2.group(1).upper()
        if candidate in _VALID_LINES:
            return candidate
    return None


def _resolve_ligne(entities: dict, message: str, history: list) -> str | None:
    """
    Résolution de la ligne en 3 niveaux :
    1. entities LLM (prioritaire)
    2. extraction regex depuis le message brut
    3. historique de conversation (multi-tour)
    """
    # Niveau 1 : LLM
    ligne = entities.get("ligne")
    if ligne and str(ligne).upper() in _VALID_LINES:
        return str(ligne).upper()

    # Niveau 2 : regex message brut
    ligne = _ligne_depuis_message(message)
    if ligne:
        return ligne

    # Niveau 3 : historique
    ligne = _ligne_depuis_historique(history)
    if ligne:
        return ligne

    return None


# ── Flow multi-tour : réponse arrêt ──────────────────────

async def handle_arret_response(phone: str, text: str, langue: str,
                                 entities: dict, history: list = None) -> str:
    ctx         = get_context(phone)
    ligne       = ctx.ligne
    signalement = ctx.signalement
    reset_context(phone)

    if not ligne or not signalement:
        if langue == "wolof":
            return "Wax ma ci bus bi ak arrêt bi 🙏"
        return "Dis-moi quel bus et à quel arrêt tu es. 🙏"

    arret_usager = (
        entities.get("origin")
        or entities.get("destination")
        or _ligne_depuis_message(text)
        or text.strip()
    )

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
        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n"
                f"Duma xam distance bi exact, waaye dafa jeex ci kanam. 🙏"
            )
        return (
            f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n"
            f"Je ne trouve pas ton arrêt exact — mais le bus avance ! 🙏"
        )

    if distance == 0:
        if langue == "wolof":
            return f"🚌 Bus *{ligne}* — dafa am ci sa arrêt *{arret_usager}* ! Jël ko ! 🏃"
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

    # Résolution robuste : LLM → regex → historique
    ligne = _resolve_ligne(entities, message, history)

    if not ligne:
        if langue == "wolof":
            return "Numéro bus bi soxor. Wax ma : *Bus 15 est où ?* 🚌"
        return "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?* 🚌"

    signalements = queries.get_signalements_actifs(ligne)

    if signalements:
        s = signalement = signalements[0]
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

    ctx = build_context(
        message=message,
        intent="question",
        contact=contact,
        ligne=ligne,
        signalements=[],
        history=history,
    )
    return await generate_response(ctx, langue, history)


# ── Liste des arrêts ──────────────────────────────────────

async def handle_liste_arrets(message: str, contact: dict, langue: str,
                               entities: dict, history: list = None) -> str:

    # Résolution robuste : LLM → regex → historique
    ligne = _resolve_ligne(entities, message, history or [])

    if not ligne:
        if langue == "wolof":
            return "Numéro ligne bi soxor. Ex : *arrêts du bus 15*"
        return "Quelle ligne ? Ex : *arrêts du bus 15*"

    info       = _NETWORK.get(ligne, {})
    stops      = info.get("stops", [])
    arrets_str = " → ".join([s["nom"] for s in stops])
    nom_ligne  = info.get("name", info.get("description", ""))

    if not arrets_str:
        return f"❌ Aucun arrêt trouvé pour la ligne *{ligne}*."

    if langue == "wolof":
        return f"🚌 Bus *{ligne}* ({nom_ligne}) :\n{arrets_str}"
    return f"🚌 *Bus {ligne}* — {nom_ligne}\nArrêts : {arrets_str}"