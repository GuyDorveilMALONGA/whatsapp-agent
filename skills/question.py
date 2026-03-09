"""
skills/question.py — V4 LLM-Driven
Répond à "le bus X est où ?" avec les signalements actifs.

V4 : entities injectées depuis route_result (main.py)
     Suppression de l'import extractor + NETWORK + VALID_LINES
     Chargement direct depuis dem_dikk_lines_gps_final.json (source de vérité)
     _calculer_distance et _bus_deja_passe réécrites sur le JSON GPS
     handle_arret_response accepte entities dict
     _ambigues_message supprimé (LLM désambiguïse en amont)

Flow multi-tour :
1. Xëtu trouve un signalement → demande l'arrêt de l'usager
2. L'usager répond son arrêt → Xëtu calcule la distance et le temps estimé
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

# ~3 minutes par arrêt en moyenne à Dakar
_MINUTES_PAR_ARRET = 3

# ── Chargement source de vérité (Règle Absolue 10) ───────
_NETWORK: dict = {}
_VALID_LINES: set = set()

try:
    with open("dem_dikk_lines_gps_final.json", "r", encoding="utf-8") as f:
        _LINES_DATA = json.load(f)
        for line in _LINES_DATA:
            num = str(line.get("number", "")).upper()
            _NETWORK[num] = line
            _VALID_LINES.add(num)
    logger.info(f"[Question] JSON chargé : {len(_VALID_LINES)} lignes")
except Exception as e:
    logger.error(f"[Question] Erreur critique chargement JSON: {e}")


# ── Calcul de distance (basé sur JSON GPS) ────────────────

def _get_stops(ligne: str) -> list[str]:
    """Retourne la liste des noms d'arrêts depuis le JSON. Règle 10 : stop['nom']."""
    line_data = _NETWORK.get(str(ligne).upper(), {})
    return [s["nom"].lower() for s in line_data.get("stops", [])]


def _calculer_distance(ligne: str, position_bus: str, arret_usager: str) -> int | None:
    """Calcule le nombre d'arrêts entre le bus et l'usager."""
    stops = _get_stops(ligne)
    if not stops:
        return None

    bus_lower    = position_bus.lower()
    usager_lower = arret_usager.lower()

    idx_bus    = next((i for i, n in enumerate(stops) if bus_lower in n or n in bus_lower), None)
    idx_cible  = next((i for i, n in enumerate(stops) if usager_lower in n or n in usager_lower), None)

    if idx_bus is None or idx_cible is None:
        return None

    dist = idx_cible - idx_bus
    return dist if dist > 0 else None


def _bus_deja_passe(ligne: str, position_bus: str, arret_usager: str) -> bool:
    """Retourne True si le bus est déjà passé à l'arrêt de l'usager."""
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


# ── Flow multi-tour : réponse arrêt ──────────────────────

async def handle_arret_response(phone: str, text: str, langue: str, entities: dict) -> str:
    """
    Appelé depuis main.py quand session est en état 'attente_arret'.
    L'usager vient de donner son arrêt.
    Priorité entités LLM → texte brut.
    """
    ctx        = get_context(phone)
    ligne      = ctx.ligne
    signalement = ctx.signalement

    reset_context(phone)

    if not ligne or not signalement:
        if langue == "wolof":
            return "Wax ma ci bus bi ak arrêt bi 🙏"
        return "Dis-moi quel bus et à quel arrêt tu es. 🙏"

    # Priorité : entités LLM → texte brut
    arret_usager = (
        entities.get("origin")
        or entities.get("destination")
        or text.strip()
    )

    position_bus = signalement.get("position", "")
    deja_passe   = _bus_deja_passe(ligne, position_bus, arret_usager)

    if deja_passe:
        if langue == "wolof":
            return (
                f"😔 Bus *{ligne}* — dafa jeex ci *{arret_usager}*.\n"
                f"Xëtu dina la wéer bu ñëw ci noppi. "
                f"Bëgg nga tappaliku ? Yëgël : *Préviens-moi pour le Bus {ligne}*"
            )
        return (
            f"😔 Le Bus *{ligne}* est déjà passé à *{arret_usager}*.\n"
            f"Xëtu te préviendra au prochain passage. "
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
            f"Je ne trouve pas ton arrêt dans le réseau — mais le bus avance ! 🙏"
        )

    if distance == 0:
        if langue == "wolof":
            return f"🚌 Bus *{ligne}* — dafa am ci sa arrêt *{arret_usager}* ! Jël ko ! 🏃"
        return f"🚌 Bus *{ligne}* est signalé à ton arrêt *{arret_usager}* ! Cours ! 🏃"

    temps = distance * _MINUTES_PAR_ARRET
    if langue == "wolof":
        return (
            f"🚌 Bus *{ligne}* ci *{position_bus}* — "
            f"{distance} arrêt(s) ci kanam (~{temps} min). Tëral ! 🙏"
        )
    return (
        f"🚌 Bus *{ligne}* est à *{position_bus}*.\n"
        f"📍 Il est à *{distance} arrêt(s)* de *{arret_usager}* (~{temps} min). Prépare-toi ! 🙏"
    )


# ── Handler principal ─────────────────────────────────────

async def handle(message: str, contact: dict, langue: str,
                 history: list, entities: dict) -> str:
    """Répond à 'Bus X est où ?' en utilisant les entités LLM."""
    ligne = entities.get("ligne")

    if not ligne:
        if langue == "wolof":
            return "Numéro bus bi soxor ci sa message. Wax ma : 'Bus [numéro] est où ?'"
        return "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?*"

    ligne = str(ligne).upper()

    if ligne not in _VALID_LINES:
        valides = ", ".join(sorted(_VALID_LINES)[:10])
        if langue == "wolof":
            return f"Ligne {ligne} — duma ko xam. Lignes yi : {valides}..."
        return (
            f"❌ La ligne *{ligne}* n'existe pas dans le réseau Dem Dikk.\n"
            f"Lignes disponibles : {valides}..."
        )

    signalements = queries.get_signalements_actifs(ligne)

    if signalements:
        s = signalements[0]
        set_attente_arret(contact["phone"], ligne, s)

        try:
            now     = datetime.now(timezone.utc)
            created = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
            minutes_ago = int((now - created).total_seconds() / 60)
            age = f"il y a {minutes_ago} min" if minutes_ago > 0 else "à l'instant"
        except Exception:
            age = "récemment"

        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* signalé ci *{s['position']}* {age}.\n"
                f"Fii nga nekk ? (wax ma sa arrêt)"
            )
        return (
            f"🚌 Bus *{ligne}* signalé à *{s['position']}* {age}.\n"
            f"Tu es à quel arrêt ? Je calcule le temps d'arrivée. 📍"
        )

    # Aucun signalement → LLM avec contexte
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
                               entities: dict) -> str:
    """Répond à 'quels sont les arrêts de la ligne X ?'"""
    ligne = entities.get("ligne")

    if not ligne or str(ligne).upper() not in _VALID_LINES:
        if langue == "wolof":
            return "Numéro ligne bi soxor. Wax ma ligne bi ?"
        return "Quelle ligne ? Ex : *arrêts du bus 15*"

    ligne    = str(ligne).upper()
    info     = _NETWORK.get(ligne, {})
    # Règle Absolue 10 : stop["nom"]
    arrets_str = " → ".join([s["nom"] for s in info.get("stops", [])])

    if langue == "wolof":
        return f"🚌 Bus {ligne} ({info.get('description', '')}) :\n{arrets_str}"
    return (
        f"🚌 *Bus {ligne}* — {info.get('description', '')}\n"
        f"Arrêts : {arrets_str}"
    )