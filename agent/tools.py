"""
agent/tools.py — V1.9
Outils LangGraph de Xëtu.

MIGRATIONS V1.9 depuis V1.8 :
  - Ajout tool set_itinerary_context (TOOL 7)
    Fixe le flux itinéraire 2 tours : quand destination connue mais origin manquante,
    l'agent appelle ce tool pour setter session.etat='attente_origin' en DB.
    Sans ce tool, set_attente_origin() n'était jamais appelé → Tour 2 impossible.
  - ALL_TOOLS mis à jour
"""
import logging
from typing import Optional, Annotated
from langchain_core.tools import tool, InjectedToolArg
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

ConfigDep = Annotated[RunnableConfig, InjectedToolArg]


def _get_phone(config: RunnableConfig) -> str:
    phone = config.get("configurable", {}).get("phone", "")
    if not phone:
        raise ValueError("phone manquant dans RunnableConfig — vérifier agent/xetu_agent.py")
    return phone


# ══════════════════════════════════════════════════════════
# HELPER — Formatage itinéraire (Markdown, max 4 lignes)
# ══════════════════════════════════════════════════════════

def _format_route_result(result: dict) -> str:
    """Transforme le dict brut de graph.find_route() en string Markdown lisible.
    Appelé uniquement par calculate_route — pas un tool LangGraph.
    """
    status = result.get("status", "error")
    routes = result.get("routes") or []

    if status == "stop_not_found":
        which = result.get("which", "")
        query = result.get("query", "?")
        label = "départ" if which == "origin" else "destination"
        return f"Je ne connais pas *{query}* comme {label}. Précise le quartier ou l'arrêt Dem Dikk. 🙏"

    if status == "same_stop":
        stop = result.get("stop", "?")
        return f"Le départ et la destination sont le même arrêt (*{stop}*). 🙏"

    if status == "not_found" or not routes:
        orig = result.get("origin_display") or result.get("origin", "?")
        dest = result.get("dest_display") or result.get("destination", "?")
        return f"Aucun itinéraire trouvé entre *{orig}* et *{dest}*. Reformule ou précise le quartier."

    r = routes[0]

    def _mins(total_min=None, nb_stops=None) -> str:
        if total_min:
            return f"~{total_min} min"
        if nb_stops:
            return f"~{nb_stops * 2} min"
        return ""

    orig = result.get("origin_display", "?")
    dest = result.get("dest_display", "?")

    if status == "direct":
        num      = r.get("number", "?")
        nb       = r.get("nb_stops")
        t_min    = r.get("total_min") or (nb * 2 if nb else None)
        duration = _mins(t_min, nb)
        stops    = r.get("stops", [])
        depart   = stops[0] if stops else orig
        arrivee  = stops[-1] if stops else dest
        dur_part = f", {duration}" if duration else ""
        return (
            f"🚌 Ligne {num} → montez à *{depart}*, "
            f"descendez à *{arrivee}* ({nb} arrêts{dur_part})"
        )

    if status == "walk_direct":
        num           = r.get("number", "?")
        walk_stop     = r.get("walk_stop", "?")
        walk_min      = r.get("walk_min")
        total_min     = r.get("total_min")
        nb            = r.get("nb_stops")
        stops         = r.get("stops", [])
        arrivee       = stops[-1] if stops else dest
        duration      = _mins(total_min, nb)
        walk_part     = f"Marchez {walk_min} min jusqu'à *{walk_stop}*" if walk_min else f"Rejoignez *{walk_stop}*"
        dur_part      = f" ({duration} total)" if duration else ""
        walk_dest_min = r.get("walk_dest_min", 0)
        if walk_dest_min:
            return (
                f"🚶 {walk_part}, puis 🚌 Ligne {num} → descendez à *{arrivee}*, "
                f"puis 🚶 {walk_dest_min} min à pied{dur_part}"
            )
        return f"🚶 {walk_part}, puis 🚌 Ligne {num} → descendez à *{arrivee}*{dur_part}"

    if status == "transfer":
        num1      = r.get("number1", "?")
        transfer  = r.get("transfer", "?")
        num2      = r.get("number2", "?")
        total_min = r.get("total_min")
        nb        = r.get("nb_stops")
        stops2    = r.get("stops2", [])
        arrivee   = stops2[-1] if stops2 else dest
        duration  = _mins(total_min, nb)
        dur_part  = f" ({duration} total)" if duration else ""
        return (
            f"🚌 Ligne {num1} → *{transfer}* (correspondance), "
            f"puis 🚌 Ligne {num2} → *{arrivee}*{dur_part}"
        )

    logger.warning(f"[_format_route_result] status inconnu: {status!r}")
    return f"Aucun itinéraire trouvé entre *{orig}* et *{dest}*. Reformule ou précise le quartier."


# ══════════════════════════════════════════════════════════
# TOOL 1 — Itinéraire
# ══════════════════════════════════════════════════════════

@tool
async def calculate_route(
    origin: str,
    destination: str,
    config: ConfigDep,
) -> str:
    """Calcule un itinéraire en bus Dem Dikk à Dakar.
    Utiliser UNIQUEMENT si l'utilisateur fournit un départ ET une destination.
    Ne pas appeler si l'une des deux est manquante — appeler set_itinerary_context à la place.
    Retourne une string Markdown prête à envoyer — ne pas reformater ni résumer.

    Args:
        origin: point de départ (quartier, arrêt ou lieu connu de Dakar)
        destination: point d'arrivée (quartier, arrêt ou lieu connu de Dakar)
    """
    from agent.graph import get_graph
    logger.info(f"[calculate_route] origin={origin!r} destination={destination!r}")
    graph = get_graph()
    try:
        result = graph.find_route(origin, destination)
        if not result:
            return (
                f"Aucun itinéraire trouvé entre *{origin}* et *{destination}*. "
                "Reformule ou précise le quartier."
            )
        msg = _format_route_result(result)
        logger.info(f"[calculate_route] → {msg[:80]!r}")
        return msg
    except Exception as e:
        logger.error(f"[calculate_route] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return (
            f"Erreur lors du calcul d'itinéraire entre *{origin}* et *{destination}*. "
            "Réessaie dans quelques secondes."
        )


# ══════════════════════════════════════════════════════════
# TOOL 2 — Signalements récents
# ══════════════════════════════════════════════════════════

@tool
async def get_recent_sightings(
    ligne: str,
    config: ConfigDep,
) -> dict:
    """Retourne les signalements récents (position des bus) pour une ligne donnée.
    Utiliser quand l'usager demande où est un bus, s'il est passé, ou à quelle heure il arrive.
    Ne pas utiliser pour signaler un bus — utiliser report_bus pour ça.

    Args:
        ligne: numéro de ligne Dem Dikk (ex: '15', '16A', '23', 'TAF TAF')
    """
    from db import queries
    from config.settings import VALID_LINES

    ligne = str(ligne).upper()
    logger.info(f"[get_recent_sightings] appelé — ligne={ligne}")

    if ligne not in VALID_LINES:
        logger.warning(f"[get_recent_sightings] ligne inconnue: {ligne!r}")
        return {"status": "unknown_line", "ligne": ligne}

    try:
        sightings = queries.get_signalements_actifs(ligne)
        logger.info(f"[get_recent_sightings] ligne={ligne} → {len(sightings)} signalement(s)")
        if not sightings:
            return {"status": "no_data", "ligne": ligne}
        results = []
        for s in sightings[:3]:
            results.append({
                "position":  s.get("position", ""),
                "timestamp": s.get("timestamp", ""),
                "qualite":   s.get("qualite"),
            })
        return {"status": "ok", "ligne": ligne, "sightings": results}
    except Exception as e:
        logger.error(f"[get_recent_sightings] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 3 — Signalement V1.5
# ══════════════════════════════════════════════════════════

@tool
async def report_bus(
    ligne: str,
    arret: str,
    message_original: str,
    config: ConfigDep,
) -> dict:
    """Enregistre qu'un usager a physiquement VU un bus à un arrêt précis.
    Utiliser UNIQUEMENT quand l'usager signale une observation directe (il voit le bus).
    NE PAS utiliser pour : questions sur l'heure, attente d'un bus, itinéraires.
    Si needs_confirmation dans la réponse : demander confirmation à l'usager,
    NE PAS rappeler report_bus automatiquement.

    Args:
        ligne: numéro de ligne Dem Dikk (ex: '15', '16A', 'TAF TAF')
        arret: nom de l'arrêt où le bus a été vu
        message_original: texte brut de l'usager (pour l'anti-fraude)
    """
    import asyncio
    from db import queries
    from config.settings import VALID_LINES
    from core.anti_fraud import is_blacklisted, is_spam_pattern, compute_confidence
    from skills.signalement import notify_abonnes

    phone = _get_phone(config)
    ligne = str(ligne).upper()
    logger.info(f"[report_bus] ligne={ligne} arret={arret!r} phone=…{phone[-4:]}")

    if ligne not in VALID_LINES:
        return {"status": "error", "message": f"Ligne {ligne} inconnue du réseau Dem Dikk"}

    if is_blacklisted(phone):
        return {"status": "blocked", "reason": "blacklist"}

    if is_spam_pattern(message_original):
        return {"status": "blocked", "reason": "spam"}

    confidence = compute_confidence(phone, ligne, arret)
    if confidence < 0.3:
        return {
            "status": "needs_confirmation",
            "ligne": ligne,
            "arret": arret,
            "confidence": confidence,
        }

    try:
        result = queries.save_signalement(ligne, arret, phone)
    except Exception as e:
        logger.error(f"[report_bus] save erreur: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    if result is None:
        return {"status": "duplicate", "ligne": ligne, "arret": arret}

    try:
        asyncio.create_task(notify_abonnes(ligne, arret, phone))
    except Exception as e:
        logger.warning(f"[report_bus] notify erreur: {e}")

    try:
        abonnes = queries.get_abonnes(ligne)
        nb_abonnes = sum(1 for a in abonnes if a["phone"] != phone)
    except Exception:
        nb_abonnes = 0

    logger.info(f"[report_bus] ✅ ligne={ligne} arret={arret} abonnes={nb_abonnes}")
    return {
        "status": "ok",
        "ligne": ligne,
        "arret": arret,
        "nb_abonnes_notifies": nb_abonnes,
    }


# ══════════════════════════════════════════════════════════
# TOOL 4 — Abonnement
# ══════════════════════════════════════════════════════════

@tool
async def manage_subscription(
    action: str,
    ligne: str,
    config: ConfigDep,
    arret: Optional[str] = None,
    heure: Optional[str] = None,
) -> dict:
    """Gère les abonnements aux alertes bus (créer ou supprimer).
    Utiliser quand l'usager veut être notifié quand un bus est signalé,
    ou quand il veut arrêter de recevoir des alertes.

    Args:
        action: 'subscribe' pour s'abonner, 'unsubscribe' pour se désabonner
        ligne: numéro de ligne Dem Dikk concernée
        arret: arrêt spécifique à surveiller (optionnel — toute la ligne si absent)
        heure: heure préférée de notification HH:MM (optionnel)
    """
    from config.settings import VALID_LINES
    from db import queries

    phone = _get_phone(config)
    ligne = str(ligne).upper()
    logger.info(f"[manage_subscription] action={action!r} ligne={ligne} phone=…{phone[-4:]}")

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
        logger.error(f"[manage_subscription] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 5 — Info réseau
# ══════════════════════════════════════════════════════════

@tool
async def get_bus_info(
    query: str,
    config: ConfigDep,
    ligne: Optional[str] = None,
) -> dict:
    """Retourne des informations sur le réseau Dem Dikk : liste des arrêts d'une ligne,
    horaires de service, fréquences, terminus. Utiliser pour répondre aux questions
    générales sur le réseau (tracé, arrêts desservis, heures de passage).

    Args:
        query: question de l'usager sur le réseau
        ligne: numéro de ligne concernée (optionnel — améliore la précision)
    """
    from core.network import NETWORK, get_stop_names
    from core.frequencies import format_service
    from rag.retriever import retrieve

    logger.info(f"[get_bus_info] query={query!r} ligne={ligne!r}")
    result = {}

    if ligne:
        ligne_up = str(ligne).upper()
        if ligne_up in NETWORK:
            result["stops"] = get_stop_names(ligne_up)
            result["service"] = format_service(ligne_up)

    try:
        rag_answer = retrieve(query, ligne=ligne)
        if rag_answer:
            result["rag"] = rag_answer
    except Exception as e:
        logger.warning(f"[get_bus_info] RAG erreur: {e}")

    return result if result else {"status": "not_found", "query": query}


# ══════════════════════════════════════════════════════════
# TOOL 6 — Extracteur entités
# ══════════════════════════════════════════════════════════

@tool
async def extract_entities(
    text: str,
    config: ConfigDep,
) -> dict:
    """Extrait le numéro de ligne et le nom d'arrêt depuis un message ambigu ou flou.
    Utiliser quand le message de l'usager contient probablement une ligne et/ou un arrêt
    mais que ce n'est pas clairement structuré (fautes, abréviations, mélange wolof/français).

    Args:
        text: message brut de l'usager à analyser
    """
    from agent.extractor import extract
    logger.info(f"[extract_entities] text={text!r}")
    result = extract(text)
    if not result:
        return {"ligne": None, "arret": None}
    return {
        "ligne":      result.ligne,
        "arret":      result.arret,
        "confidence": getattr(result, "confidence", 1.0),
    }


# ══════════════════════════════════════════════════════════
# TOOL 7 — Contexte itinéraire (flux 2 tours)
# ══════════════════════════════════════════════════════════

@tool
async def set_itinerary_context(
    destination: str,
    config: ConfigDep,
) -> str:
    """Appeler quand l'usager veut aller quelque part mais n'a PAS donné son point de départ.
    Enregistre la destination en session et prépare le flux 2 tours.
    NE PAS appeler si départ ET destination sont déjà connus — utiliser calculate_route directement.
    Retourne 'ok' — le LLM demande ensuite 'Tu pars d'où ?' en langage naturel.

    Args:
        destination: lieu de destination mentionné par l'usager (ex: 'Sandaga', 'UCAD', 'Yoff')
    """
    from core.session_manager import set_attente_origin

    phone = _get_phone(config)
    destination = destination.strip()

    if not destination:
        logger.warning("[set_itinerary_context] destination vide — ignoré")
        return "error: destination vide"

    logger.info(
        f"[set_itinerary_context] phone=…{phone[-4:]} destination={destination!r}"
    )

    try:
        set_attente_origin(phone, destination)
        logger.info(
            f"[set_itinerary_context] ✅ session.etat='attente_origin' "
            f"destination={destination!r}"
        )
        return "ok"
    except Exception as e:
        logger.error(
            f"[set_itinerary_context] ERREUR: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return f"error: {e}"


# ══════════════════════════════════════════════════════════
# Export
# ══════════════════════════════════════════════════════════

ALL_TOOLS = [
    calculate_route,
    get_recent_sightings,
    report_bus,
    manage_subscription,
    get_bus_info,
    extract_entities,
    set_itinerary_context,  # V1.9 — flux itinéraire 2 tours
]