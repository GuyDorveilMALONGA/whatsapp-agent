"""
skills/question.py
Répond à "le bus X est où ?" avec les signalements actifs.

Flow multi-tour :
1. Sëtu trouve un signalement → demande l'arrêt de l'usager
2. L'usager répond son arrêt → Sëtu calcule la distance et le temps estimé
"""
from datetime import datetime, timezone
from db import queries
from agent.extractor import extract, VALID_LINES, NETWORK
from agent.llm_brain import generate_response
from core.context_builder import build_context
from core.session_manager import (
    get_context, set_attente_arret,
    reset_context, is_waiting_for_arret
)

# ~3 minutes par arrêt en moyenne à Dakar
_MINUTES_PAR_ARRET = 3


def _ambigues_message(ambigues: list[str], langue: str) -> str:
    options = "\n".join([
        f"• *{l}* — {NETWORK[l].get('description', '')}" for l in ambigues
    ])
    if langue == "wolof":
        return f"Bus bii — numéro yi ngi ci :\n{options}\nWax ma lignes bi ?"
    return f"Quel bus exactement ?\n{options}"


async def handle_arret_response(phone: str, text: str, langue: str) -> str:
    """
    Appelé depuis main.py quand session est en état 'attente_arret'.
    L'usager vient de donner son arrêt — on calcule la distance.
    """
    ctx = get_context(phone)
    ligne = ctx.ligne
    signalement = ctx.signalement

    # Reset immédiat — on ne reste pas en attente
    reset_context(phone)

    if not ligne or not signalement:
        if langue == "wolof":
            return "Wax ma ci bus bi ak arrêt bi 🙏"
        return "Dis-moi quel bus et à quel arrêt tu es. 🙏"

    # Extrait l'arrêt depuis la réponse de l'usager
    result = extract(text)
    arret_usager = result.arret_normalise or result.arret

    if not arret_usager:
        # Essai direct : le texte entier comme nom d'arrêt
        arret_usager = text.strip()

    position_bus = signalement.get("position", "")
    distance = _calculer_distance(ligne, position_bus, arret_usager)

    # Construit la réponse
    # Vérifie si le bus est déjà passé
    deja_passe = _bus_deja_passe(ligne, position_bus, arret_usager)

    if deja_passe:
        if langue == "wolof":
            return (
                f"😔 Bus *{ligne}* — dafa jeex ci *{arret_usager}*.\n"
                f"Sëtu dina la wéer bu ñëw ci noppi. "
                f"Bëgg nga tappaliku ? Yëgël : *Préviens-moi pour le Bus {ligne}*"
            )
        return (
            f"😔 Le Bus *{ligne}* est déjà passé à *{arret_usager}*.\n"
            f"Sëtu te préviendra au prochain passage. "
            f"Tu veux t\'abonner ? Envoie : *Préviens-moi pour le Bus {ligne}*"
        )

    if distance is None:
        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n"
                f"Duma xam distance bi exact, waaye dafa jeex ci kanam. 🙏"
            )
        return (
            f"🚌 Bus *{ligne}* signalé à *{position_bus}*.\n"
            f"Je ne trouve pas ton arrêt dans le réseau — "
            f"mais le bus avance ! 🙏"
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
        f"📍 Il est à *{distance} arrêt(s)* de *{arret_usager}* "
        f"(~{temps} min). Prépare-toi ! 🙏"
    )


async def handle(message: str, contact: dict, langue: str,
                 history: list | None = None) -> str:
    result = extract(message)

    # Ambiguïté (ex: 16A ou 16B)
    if result.ambigues:
        return _ambigues_message(result.ambigues, langue)

    # Ligne inconnue
    if result.ligne and not result.ligne_valide:
        valides = ", ".join(sorted(VALID_LINES)[:10])
        if langue == "wolof":
            return f"Ligne {result.ligne} — duma ko xam. Lignes yi : {valides}..."
        return (
            f"❌ La ligne *{result.ligne}* n'existe pas dans le réseau Dem Dikk.\n"
            f"Lignes disponibles : {valides}..."
        )

    # Pas de ligne détectée
    if not result.ligne:
        if langue == "wolof":
            return "Numéro bus bi soxor ci sa message. Wax ma : 'Bus [numéro] est où ?'"
        return "Quel numéro de bus cherches-tu ? Ex : *Bus 15 est où ?*"

    # Cherche signalements actifs
    signalements = queries.get_signalements_actifs(result.ligne)

    if signalements:
        s = signalements[0]

        # Passe en état attente_arret
        set_attente_arret(contact["phone"], result.ligne, s)

        # Demande l'arrêt de l'usager
        try:
            now = datetime.now(timezone.utc)
            created = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
            minutes_ago = int((now - created).total_seconds() / 60)
            age = f"il y a {minutes_ago} min" if minutes_ago > 0 else "à l'instant"
        except Exception:
            age = "récemment"

        if langue == "wolof":
            return (
                f"🚌 Bus *{result.ligne}* signalé ci *{s['position']}* {age}.\n"
                f"Fii nga nekk ? (wax ma sa arrêt)"
            )
        return (
            f"🚌 Bus *{result.ligne}* signalé à *{s['position']}* {age}.\n"
            f"Tu es à quel arrêt ? Je calcule le temps d'arrivée. 📍"
        )

    # Aucun signalement → LLM
    ctx = build_context(
        message=message,
        intent="question",
        contact=contact,
        ligne=result.ligne,
        signalements=[],
        history=history,
    )
    return await generate_response(ctx, langue, history)


async def handle_liste_arrets(message: str, contact: dict, langue: str) -> str:
    """Répond à 'quels sont les arrêts de la ligne X ?'"""
    from agent.extractor import get_arrets_ligne
    result = extract(message)

    if result.ambigues:
        return _ambigues_message(result.ambigues, langue)

    if not result.ligne or not result.ligne_valide:
        if langue == "wolof":
            return "Numéro ligne bi soxor. Wax ma ligne bi ?"
        return "Quelle ligne ? Ex : *arrêts du bus 15*"

    info = get_arrets_ligne(result.ligne)
    arrets_str = " → ".join(info.get("aller", []))

    if langue == "wolof":
        return f"🚌 Bus {result.ligne} ({info.get('description', '')}) :\n{arrets_str}"
    return (
        f"🚌 *Bus {result.ligne}* — {info.get('description', '')}\n"
        f"Arrêts : {arrets_str}"
    )


# ── Calcul de distance ────────────────────────────────────

def _calculer_distance(ligne: str, position_bus: str, arret_usager: str) -> int | None:
    """
    Calcule le nombre d'arrêts entre le bus et l'usager.
    Teste aller et retour, retourne le minimum.
    """
    ligne_data = NETWORK.get(ligne, {})
    arrets_aller = [a.lower() for a in ligne_data.get("arrets_aller", [])]
    arrets_retour = [a.lower() for a in ligne_data.get("arrets_retour", [])]

    bus_lower = position_bus.lower()
    usager_lower = arret_usager.lower()

    dist_aller = _distance(bus_lower, usager_lower, arrets_aller)
    dist_retour = _distance(bus_lower, usager_lower, arrets_retour)

    distances = [d for d in [dist_aller, dist_retour] if d is not None]
    return min(distances) if distances else None


def _distance(arret_bus: str, arret_cible: str, liste: list[str]) -> int | None:
    """Distance entre deux arrêts dans une liste ordonnée."""
    try:
        idx_bus = next(
            (i for i, a in enumerate(liste) if arret_bus in a or a in arret_bus), None
        )
        idx_cible = next(
            (i for i, a in enumerate(liste) if arret_cible in a or a in arret_cible), None
        )
        if idx_bus is None or idx_cible is None:
            return None
        if idx_bus > idx_cible:
            return None  # Bus déjà passé
        return idx_cible - idx_bus
    except Exception:
        return None

def _bus_deja_passe(ligne: str, position_bus: str, arret_usager: str) -> bool:
    """
    Retourne True si le bus est déjà passé à l'arrêt de l'usager.
    Vérifie dans les deux sens (aller + retour).
    """
    ligne_data = NETWORK.get(ligne, {})
    arrets_aller = [a.lower() for a in ligne_data.get("arrets_aller", [])]
    arrets_retour = [a.lower() for a in ligne_data.get("arrets_retour", [])]
    bus_lower = position_bus.lower()
    usager_lower = arret_usager.lower()

    for liste in [arrets_aller, arrets_retour]:
        idx_bus = next((i for i, a in enumerate(liste) if bus_lower in a or a in bus_lower), None)
        idx_cible = next((i for i, a in enumerate(liste) if usager_lower in a or a in usager_lower), None)
        if idx_bus is not None and idx_cible is not None:
            if idx_bus > idx_cible:
                return True  # Bus après la cible → déjà passé
    return False