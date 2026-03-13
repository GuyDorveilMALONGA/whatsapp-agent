"""
agent/tools.py — V1.0
Skills Xëtu → Tools LangGraph.
Le numéro de téléphone est injecté via RunnableConfig,
pas extrait par le LLM — zéro risque de fuite ou d'erreur.
"""
from typing import Optional
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig


def _get_phone(config: RunnableConfig) -> str:
    """Récupère le phone depuis le config injecté par l'agent."""
    phone = config.get("configurable", {}).get("phone", "")
    if not phone:
        raise ValueError("phone manquant dans RunnableConfig — vérifier agent/xetu_agent.py")
    return phone


# ══════════════════════════════════════════════════════════
# TOOL 1 — Itinéraire
# ══════════════════════════════════════════════════════════

@tool
def calculate_route(origin: str, destination: str, config: RunnableConfig) -> dict:
    """Calcule un itinéraire en bus à Dakar entre deux points.
    À utiliser quand l'utilisateur veut aller quelque part,
    demande comment rejoindre un endroit, ou quelle ligne prendre.

    Args:
        origin: Point de départ (quartier, arrêt ou adresse)
        destination: Point d'arrivée (quartier, arrêt ou adresse)
    """
    from agent.graph import get_graph
    graph = get_graph()
    result = graph.find_route(origin, destination)
    if not result or not result.get("routes"):
        return {"status": "not_found", "origin": origin, "destination": destination}
    return {"status": "ok", "result": result}


# ══════════════════════════════════════════════════════════
# TOOL 2 — Signalement
# ══════════════════════════════════════════════════════════

@tool
async def report_bus(ligne: str, arret: str, message_original: str, config: RunnableConfig) -> dict:
    """Enregistre un signalement : un utilisateur a VU un bus à un arrêt maintenant.
    À utiliser uniquement pour une observation directe au présent.
    NE PAS utiliser si l'utilisateur dit 'j'attends', 'je prends', ou pose une question.

    Args:
        ligne: Numéro de ligne vu (ex: '7', '15', 'DDD')
        arret: Arrêt où le bus a été observé
        message_original: Texte brut du message pour validation anti-fraude
    """
    from core.anti_fraud import is_blacklisted_signalement
    from config.settings import VALID_LINES
    from db import queries

    phone = _get_phone(config)

    if is_blacklisted_signalement(message_original):
        return {"status": "rejected", "reason": "not_a_real_sighting"}

    ligne = str(ligne).upper()
    if ligne not in VALID_LINES:
        return {"status": "error", "message": f"Ligne {ligne} inconnue du réseau Dem Dikk"}

    try:
        queries.save_sighting(phone, ligne, arret)
        return {"status": "ok", "ligne": ligne, "arret": arret}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 3 — Abonnement
# ══════════════════════════════════════════════════════════

@tool
async def manage_subscription(
    action: str,
    ligne: str,
    config: RunnableConfig,
    arret: Optional[str] = None,
    heure: Optional[str] = None,
) -> dict:
    """Crée ou supprime une alerte bus pour l'utilisateur.
    À utiliser quand l'utilisateur veut être notifié quand un bus passe,
    ou veut annuler une alerte existante.

    Args:
        action: 'subscribe' pour créer, 'unsubscribe' pour annuler
        ligne: Numéro de ligne (ex: '7', '15')
        arret: Arrêt de référence (optionnel)
        heure: Heure d'alerte format HH:MM (optionnel)
    """
    from config.settings import VALID_LINES
    from db import queries

    phone = _get_phone(config)
    ligne = str(ligne).upper()

    if ligne not in VALID_LINES:
        return {"status": "error", "message": f"Ligne {ligne} inconnue"}

    try:
        if action == "subscribe":
            queries.create_abonnement(phone, ligne, arret or "", heure)
            return {"status": "ok", "action": "subscribed", "ligne": ligne}
        elif action == "unsubscribe":
            queries.delete_abonnement(phone, ligne)
            return {"status": "ok", "action": "unsubscribed", "ligne": ligne}
        else:
            return {"status": "error", "message": f"Action inconnue : {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 4 — Info réseau
# ══════════════════════════════════════════════════════════

@tool
def get_bus_info(query: str, config: RunnableConfig, ligne: Optional[str] = None) -> dict:
    """Répond aux questions sur le réseau Dem Dikk :
    arrêts d'une ligne, fréquences, horaires de service, tarifs.
    À utiliser pour toute question informative sur le réseau.

    Args:
        query: Question posée par l'utilisateur
        ligne: Numéro de ligne si déjà identifié (optionnel)
    """
    from core.network import NETWORK, get_stop_names
    from core.frequencies import format_service
    from rag.retriever import retrieve

    result = {}

    if ligne:
        ligne_up = str(ligne).upper()
        if ligne_up in NETWORK:
            result["stops"] = get_stop_names(ligne_up)
            result["service"] = format_service(ligne_up)

    rag_answer = retrieve(query)
    if rag_answer:
        result["rag"] = rag_answer

    return result if result else {"status": "not_found", "query": query}


# ══════════════════════════════════════════════════════════
# TOOL 5 — Extracteur entités
# ══════════════════════════════════════════════════════════

@tool
def extract_entities(text: str, config: RunnableConfig) -> dict:
    """Extrait le numéro de ligne et le nom d'arrêt depuis un message.
    À appeler en premier sur tout message mentionnant un bus ou un arrêt.

    Args:
        text: Message brut de l'utilisateur
    """
    from agent.extractor import extract
    result = extract(text)
    if not result:
        return {"ligne": None, "arret": None}
    return {
        "ligne": result.ligne,
        "arret": result.arret,
        "confidence": getattr(result, "confidence", 1.0),
    }


# ══════════════════════════════════════════════════════════
# Export
# ══════════════════════════════════════════════════════════

ALL_TOOLS = [
    calculate_route,
    report_bus,
    manage_subscription,
    get_bus_info,
    extract_entities,
]