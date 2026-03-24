"""
agent/tools.py — V8.3
6 tools LangGraph pour l'agent Xëtu.

MIGRATIONS V8.3 depuis V8.2 :
  - report_bus : retourne minutes_ago (âge du signalement en minutes)
    L'agent peut ainsi dire "Bus 15 signalé à Liberté 4 il y a 2 min"
  - report_bus : status "duplicate" renommé "already_reported" pour clarté
    Couvre les 2 cas : doublon strict (même phone) et doublon communautaire
"""
import logging
from typing import Optional, Annotated
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

ConfigDep = Annotated[RunnableConfig, InjectedState]


def _get_phone(config: RunnableConfig) -> str:
    try:
        return config["configurable"]["thread_id"]
    except (KeyError, TypeError):
        return "unknown"


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


def _format_route_result(result: dict) -> str:
    """Formate le résultat de find_route en message WhatsApp."""
    if not result:
        return "Aucun itinéraire trouvé."

    lines = []
    segments = result.get("segments", [])

    for i, seg in enumerate(segments, 1):
        ligne     = seg.get("ligne", "?")
        origin    = seg.get("origin", "?")
        dest      = seg.get("destination", "?")
        duration  = seg.get("duration_min")
        walk_pre  = seg.get("walk_before_m")
        walk_post = seg.get("walk_after_m")

        if walk_pre and walk_pre > 0:
            lines.append(f"🚶 Marche ~{int(walk_pre)}m jusqu'à l'arrêt")

        dur_str = f" (~{duration} min)" if duration else ""
        lines.append(f"🚌 Bus *{ligne}* : {origin} → {dest}{dur_str}")

        if walk_post and walk_post > 0:
            lines.append(f"🚶 Marche ~{int(walk_post)}m à l'arrivée")

    total = result.get("total_duration_min")
    if total:
        lines.append(f"\n⏱ Durée totale estimée : ~{total} min")

    transfers = len(segments) - 1
    if transfers > 0:
        lines.append(f"🔄 {transfers} correspondance{'s' if transfers > 1 else ''}")

    return "\n".join(lines)


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

        from datetime import datetime, timezone
        now     = datetime.now(timezone.utc)
        results = []
        for s in sightings[:3]:
            minutes_ago = 0
            try:
                ts = datetime.fromisoformat(s["timestamp"].replace("Z", "+00:00"))
                minutes_ago = int((now - ts).total_seconds() / 60)
            except Exception:
                pass
            results.append({
                "position":    s.get("position", ""),
                "timestamp":   s.get("timestamp", ""),
                "minutes_ago": minutes_ago,
                "qualite":     s.get("qualite"),
            })
        return {"status": "ok", "ligne": ligne, "sightings": results}
    except Exception as e:
        logger.error(f"[get_recent_sightings] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 3 — Signalement V8.3
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
    from datetime import datetime, timezone
    from db import queries
    from config.settings import VALID_LINES
    from core.anti_fraud import (
        is_blacklisted_signalement, is_spam_pattern,
        compute_signalement_confidence, CONFIDENCE_THRESHOLD,
    )
    from skills.signalement import notify_abonnes

    phone = _get_phone(config)
    ligne = str(ligne).upper()
    logger.info(f"[report_bus] ligne={ligne} arret={arret!r} phone=…{phone[-4:]}")

    if ligne not in VALID_LINES:
        return {"status": "error", "message": f"Ligne {ligne} inconnue du réseau Dem Dikk"}

    if is_blacklisted_signalement(message_original):
        return {"status": "blocked", "reason": "blacklist"}

    if is_spam_pattern(phone, ligne):
        return {"status": "blocked", "reason": "spam"}

    confidence = compute_signalement_confidence(
        phone=phone, ligne=ligne, arret=arret,
        source="signalement_fort",
        has_verbe_observation=True,
        has_arret_connu=bool(arret),
    )

    if confidence < CONFIDENCE_THRESHOLD:
        return {
            "status":     "needs_confirmation",
            "ligne":      ligne,
            "arret":      arret,
            "confidence": round(confidence, 2),
        }

    try:
        result = queries.save_signalement(ligne, arret, phone)
    except Exception as e:
        logger.error(f"[report_bus] save erreur: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

    # Doublon strict ou doublon communautaire — même réponse UX
    if result is None:
        return {
            "status":  "already_reported",
            "ligne":   ligne,
            "arret":   arret,
            "message": "Ce bus vient d'être signalé ici par la communauté.",
        }

    try:
        asyncio.create_task(notify_abonnes(ligne, arret, phone))
    except Exception as e:
        logger.warning(f"[report_bus] notify erreur: {e}")

    try:
        abonnes    = queries.get_abonnes(ligne)
        nb_abonnes = sum(1 for a in abonnes if a["phone"] != phone)
    except Exception:
        nb_abonnes = 0

    # V8.3 : calcul âge du signalement pour réponse naturelle ("il y a X min")
    minutes_ago = 0
    if result and result.get("timestamp"):
        try:
            ts          = datetime.fromisoformat(result["timestamp"].replace("Z", "+00:00"))
            minutes_ago = int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
        except Exception:
            minutes_ago = 0

    logger.info(f"[report_bus] ✅ ligne={ligne} arret={arret} abonnes={nb_abonnes} minutes_ago={minutes_ago}")
    return {
        "status":              "ok",
        "ligne":               ligne,
        "arret":               arret,
        "minutes_ago":         minutes_ago,
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
        query: type d'info demandée ('arrêts', 'horaires', 'fréquence', 'terminus', ou question libre)
        ligne: numéro de ligne concernée (optionnel si question générale)
    """
    from core.network import get_stops, get_graph_data
    from rag.retriever import retrieve

    if ligne:
        ligne = str(ligne).upper()

    logger.info(f"[get_bus_info] query={query!r} ligne={ligne}")

    try:
        # Arrêts d'une ligne
        if ligne and any(k in query.lower() for k in ("arrêt", "arret", "stop", "passe", "dessert", "tracé", "trace")):
            stops = get_stops(ligne)
            if not stops:
                return {"status": "no_data", "ligne": ligne, "message": f"Aucun arrêt trouvé pour la ligne {ligne}"}
            return {"status": "ok", "ligne": ligne, "arrêts": stops[:30]}

        # RAG pour questions complexes
        rag_result = retrieve(query, ligne)
        if rag_result:
            return {"status": "ok", "source": "rag", "answer": rag_result}

        # Fallback graph data
        if ligne:
            data = get_graph_data(ligne)
            if data:
                return {"status": "ok", "ligne": ligne, "data": data}

        return {"status": "no_data", "message": "Aucune information disponible pour cette requête."}

    except Exception as e:
        logger.error(f"[get_bus_info] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


# ══════════════════════════════════════════════════════════
# TOOL 6 — Extraction entités
# ══════════════════════════════════════════════════════════

@tool
async def extract_entities(
    text: str,
    config: ConfigDep,
) -> dict:
    """Extrait ligne et arrêt depuis un message ambigu ou mal structuré.
    Utiliser quand le message ne correspond à aucun pattern clair.

    Args:
        text: message brut de l'usager
    """
    from agent.extractor import extract_from_text

    logger.info(f"[extract_entities] text={text[:60]!r}")
    try:
        result = extract_from_text(text)
        return result or {"status": "no_entities"}
    except Exception as e:
        logger.error(f"[extract_entities] ERREUR: {type(e).__name__}: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


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
]