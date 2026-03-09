"""
skills/itineraire.py — V4.2
Calcule et formate les itinéraires avec le moteur Walk-Aware.

FIX V4.2 :
  1. handle_origin_response : destination remontée depuis history ROBUSTE
     - V4.1 cherchait uniquement "Tu veux aller à *X*" (FR seulement)
     - V4.2 : _destination_depuis_history() — 3 patterns (FR + WO + context_builder)
     - Import re sorti du bloc (était dans la boucle en V4.1 — bug latent)

  2. handle_alternatives : NOUVEAU
     - Relance find_route() avec exclude_lines → jamais de prose LLM
     - Session sauvegardée avec origin/dest/exclude_lines après chaque itinéraire
     - Fallback history si session expirée

FIX V4.1 :
  - handle_origin_response : extractor.extract() supprimé
  - history passé en paramètre depuis main.py
"""
import re
import logging
from agent.graph import get_graph
from core.session_manager import set_attente_origin, get_context, reset_context, set_session
from rag.validator import validate_and_suggest

logger = logging.getLogger(__name__)


# ── Formatage FR ──────────────────────────────────────────

def _direct_fr(r: dict) -> str:
    best  = r["routes"][0]
    other = r["routes"][1:]
    lines = [
        f"🚌 *Ligne {best['number']}* — direct",
        f"De *{r['origin_display']}* → *{r['dest_display']}*",
        f"Durée : ~{best['nb_stops'] * 2} min · {best['nb_stops']} arrêts",
    ]
    if other:
        autres = ' · '.join(f"Ligne {x['number']}" for x in other[:2])
        lines.append(f"_Aussi : {autres}_")
    lines.append("\n— *Xëtu*")
    return "\n".join(lines)


def _walk_direct_fr(r: dict) -> str:
    best  = r["routes"][0]
    other = r["routes"][1:]
    lines = [f"🚶 {best['walk_min']} min → *{best['walk_stop']}*"]
    lines.append(f"🚌 *Ligne {best['number']}* · {best['nb_stops'] * 2} min")
    if best.get("walk_dest_m", 0) > 0:
        lines.append(f"🚶 {best['walk_dest_min']} min → *{r['dest_display']}*")
    lines.append(f"Total *~{best['total_min']} min*")
    if r.get("alt_transfer"):
        t = r["alt_transfer"]
        lines.append(
            f"\n_Option B : Ligne {t['number1']} → Ligne {t['number2']} · ~{t['total_min']} min_"
        )
    elif other:
        autres = ' · '.join(f"Ligne {x['number']}" for x in other[:2])
        lines.append(f"\n_Aussi : {autres}_")
    lines.append("\n— *Xëtu*")
    return "\n".join(lines)


def _transfer_fr(r: dict) -> str:
    best = r["routes"][0]
    lines = [
        f"🚌 *Ligne {best['number1']}* depuis *{r['origin_display']}*",
        f"↳ Descends à *{best['transfer']}* (correspondance)",
        f"🚌 *Ligne {best['number2']}* jusqu'à *{r['dest_display']}*",
        f"Total *~{best['total_min']} min*",
    ]
    if r.get("alt_walk"):
        w = r["alt_walk"]
        lines.append(
            f"\n_Option B : Marche {w['walk_min']} min → {w['walk_stop']} · "
            f"Ligne {w['number']} · ~{w['total_min']} min_"
        )
    lines.append("\n— *Xëtu*")
    return "\n".join(lines)


def _not_found_fr(r: dict) -> str:
    return (
        f"❌ Aucun trajet trouvé entre *{r['origin_display']}* "
        f"et *{r['dest_display']}*.\n\n"
        "Essaie Yango pour ce trajet. 🚗\n\n— *Xëtu*"
    )


def _no_transfer_not_found_fr(r: dict) -> str:
    return (
        f"❌ Aucun bus direct entre *{r['origin_display']}* "
        f"et *{r['dest_display']}*, même en marchant un peu.\n\n"
        "Tu veux que je cherche avec une correspondance ?\n\n— *Xëtu*"
    )


def _stop_not_found_fr(r: dict) -> str:
    which = "départ" if r.get("which") == "origin" else "destination"
    return (
        f"❓ Je ne connais pas *{r['query']}* comme arrêt de {which}.\n\n"
        "Essaie : _Terminus Leclerc · Sandaga · Yoff Village · UCAD · Colobane_\n\n"
        "— *Xëtu*"
    )


def _no_od_fr() -> str:
    return (
        "Pour un itinéraire, dis-moi d'où et où tu vas.\n\n"
        "Exemple : _Yoff → Sandaga_ ou _Comment aller à UCAD ?_\n\n— *Xëtu*"
    )


def _ask_origin_fr(dest: str) -> str:
    return f"Tu veux aller à *{dest}*.\n\nTu es à quel arrêt en ce moment ?"


# ── Formatage Wolof ───────────────────────────────────────

def _direct_wo(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚌 *Ligne {best['number']}* la jëf.",
        f"Dëkk ci *{r['origin_display']}*, dem *{r['dest_display']}*.",
        f"Jamm : ~{best['nb_stops'] * 2} min · {best['nb_stops']} areet.",
        "\n— *Xëtu*",
    ])


def _walk_direct_wo(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚶 Dem ak tank {best['walk_min']} min → *{best['walk_stop']}*",
        f"🚌 *Ligne {best['number']}* · {best['nb_stops'] * 2} min",
        f"Jamm : ~{best['total_min']} min",
        "\n— *Xëtu*",
    ])


def _transfer_wo(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚌 Jël *Ligne {best['number1']}* ci *{r['origin_display']}*.",
        f"↳ Surfu ci *{best['transfer']}*.",
        f"🚌 Jël *Ligne {best['number2']}*, dem *{r['dest_display']}*.",
        f"Jamm : ~{best['total_min']} min.",
        "\n— *Xëtu*",
    ])


def _not_found_wo(r: dict) -> str:
    return (
        f"❌ Amul yoon bi ci *{r['origin_display']}* ñëw *{r['dest_display']}*.\n\n"
        "Jël taxi Yango. 🚗\n\n— *Xëtu*"
    )


# ── Table dispatch ────────────────────────────────────────

_FMT = {
    "fr": {
        "direct":                _direct_fr,
        "walk_direct":           _walk_direct_fr,
        "transfer":              _transfer_fr,
        "not_found":             _not_found_fr,
        "no_transfer_not_found": _no_transfer_not_found_fr,
        "stop_not_found":        _stop_not_found_fr,
        "same_stop":             lambda r: f"Tu es déjà à *{r['stop']}* 😄\n\n— *Xëtu*",
    },
    "wo": {
        "direct":                _direct_wo,
        "walk_direct":           _walk_direct_wo,
        "transfer":              _transfer_wo,
        "not_found":             _not_found_wo,
        "no_transfer_not_found": _not_found_wo,
        "stop_not_found":        _stop_not_found_fr,
        "same_stop":             lambda r: f"Dëkk nga fi ci *{r['stop']}* 😄\n\n— *Xëtu*",
    },
}


# ── Extraction destination depuis historique ──────────────

def _destination_depuis_history(history: list) -> str | None:
    """
    3 patterns dans l'ordre de priorité :
      1. Bot FR  : "Tu veux aller à *Sandaga*"
      2. Bot WO  : "fa nga dem *Sandaga*"
      3. Bot     : "→ *Sandaga*" (format réponse itinéraire)
    """
    for msg in reversed(history or []):
        content = msg.get("content", "")
        if msg.get("role") != "assistant":
            continue
        m = re.search(r"Tu veux aller à \*(.+?)\*", content)
        if m:
            return m.group(1)
        m = re.search(r"fa nga dem \*(.+?)\*", content, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"→ \*(.+?)\*", content)
        if m:
            return m.group(1)
    return None


# ── Point d'entrée principal ──────────────────────────────

async def handle(message: str, contact: dict, langue: str, entities: dict) -> str:
    lang         = langue if langue in _FMT else "fr"
    graph        = get_graph()
    no_transfer  = entities.get("no_transfer_preference", False)
    origin_query = entities.get("origin")
    dest_query   = entities.get("destination")

    if not dest_query:
        return _no_od_fr() if lang == "fr" else (
            "Wax ma fi nga dëkk ak fa nga dem. Xeeti : _Yoff → Sandaga_\n\n— *Xëtu*"
        )

    if not origin_query:
        set_attente_origin(contact["phone"], dest_query)
        return _ask_origin_fr(dest_query.title()) if lang == "fr" else (
            f"Fa nga dem *{dest_query.title()}* — fi nga dëkk ?"
        )

    result = graph.find_route(origin_query, dest_query, no_transfer=no_transfer)

    # Sauvegarder origin/dest dans session pour les alternatives
    if result["status"] in ("direct", "walk_direct", "transfer"):
        _save_itineraire_session(
            contact["phone"], result, origin_query, dest_query
        )

    fmt_fn = _FMT.get(lang, _FMT["fr"]).get(result["status"])
    if fmt_fn:
        return fmt_fn(result)

    logger.error(f"[Itinéraire] Status inconnu: {result['status']}")
    return _not_found_fr(result) if lang == "fr" else _not_found_wo(result)


def _save_itineraire_session(phone: str, result: dict,
                              origin: str, dest: str):
    """Sauvegarde origin/dest/lignes proposées pour handle_alternatives."""
    routes     = result.get("routes", [])
    lignes     = []
    for r in routes:
        for key in ("number", "number1", "number2"):
            if r.get(key):
                lignes.append(r[key])
    set_session(
        phone,
        etat="itineraire_actif",
        ligne=lignes[0] if lignes else None,
        destination=dest,
        signalement={"origin": origin, "dest": dest, "exclude_lines": lignes}
    )


# ── Flow multi-tour : réponse origine ────────────────────

async def handle_origin_response(phone: str, text: str, langue: str,
                                  entities: dict, history: list = None) -> str:
    ctx         = get_context(phone)
    destination = ctx.destination
    reset_context(phone)

    # FIX V4.2 : session expirée → 3 patterns de recherche dans history
    if not destination and history:
        destination = _destination_depuis_history(history)
        if destination:
            logger.info(f"[Itinéraire] destination récupérée depuis history: {destination}")

    if not destination:
        return _no_od_fr() if langue != "wo" else (
            "Wax ma fi nga dëkk ak fa nga dem.\n\n— *Xëtu*"
        )

    origin_raw   = entities.get("origin") or entities.get("destination") or text.strip()
    origin_query = validate_and_suggest(origin_raw) or origin_raw

    no_transfer  = entities.get("no_transfer_preference", False)
    lang         = langue if langue in _FMT else "fr"
    graph        = get_graph()
    route_result = graph.find_route(origin_query, destination, no_transfer=no_transfer)

    if route_result["status"] == "stop_not_found" and route_result.get("which") == "origin":
        if lang == "fr":
            return (
                f"❓ Je ne connais pas *{origin_query}* comme arrêt Dem Dikk.\n\n"
                "Essaie : _Liberté 6 · Sandaga · Yoff Village · UCAD · Colobane_\n\n"
                "— *Xëtu*"
            )
        return (
            f"❓ Duma xam *{origin_query}* ci arrêts Dem Dikk yi.\n\n"
            "Jëfandikoo : _Liberté 6 · Sandaga · Yoff Village_\n\n— *Xëtu*"
        )

    if route_result["status"] in ("direct", "walk_direct", "transfer"):
        _save_itineraire_session(phone, route_result, origin_query, destination)

    fmt_fn = _FMT.get(lang, _FMT["fr"]).get(route_result["status"])
    if fmt_fn:
        return fmt_fn(route_result)

    return _not_found_fr(route_result) if lang == "fr" else _not_found_wo(route_result)


# ── Alternatives ──────────────────────────────────────────

async def handle_alternatives(phone: str, langue: str, history: list) -> str:
    """
    FIX V4.2 — NOUVEAU.
    Relance find_route() en excluant les lignes déjà proposées.
    Jamais de prose LLM — réponse structurée directe.

    Appelé depuis main.py/_dispatch quand intent = "alternatives_itineraire".
    """
    lang         = langue if langue in _FMT else "fr"
    graph        = get_graph()
    ctx          = get_context(phone)
    session_data = ctx.signalement or {}

    origin_query  = session_data.get("origin")
    dest_query    = session_data.get("dest") or ctx.destination
    exclude_lines = session_data.get("exclude_lines", [])

    # Fallback history si session expirée
    if not dest_query and history:
        dest_query = _destination_depuis_history(history)

    if not origin_query or not dest_query:
        return (
            "Je n'ai plus le contexte de ton dernier itinéraire.\n\n"
            "Dis-moi : _De [départ] à [destination]_\n\n— *Xëtu*"
            if lang == "fr" else
            "Wax ma ci kanam : _Fi → Fa_\n\n— *Xëtu*"
        )

    result = graph.find_route(
        origin_query, dest_query,
        exclude_lines=exclude_lines
    )

    if result["status"] in ("not_found", "no_transfer_not_found"):
        return (
            f"❌ Plus d'autres options entre *{origin_query}* "
            f"et *{dest_query}*.\n\nEssaie Yango. 🚗\n\n— *Xëtu*"
            if lang == "fr" else
            f"❌ Amul alternatives ci *{origin_query}* → *{dest_query}*.\n\n"
            "Jël Yango. 🚗\n\n— *Xëtu*"
        )

    # Mettre à jour exclude_lines pour une prochaine demande
    new_excludes = list(exclude_lines)
    for route in result.get("routes", []):
        for key in ("number", "number1", "number2"):
            if route.get(key) and route[key] not in new_excludes:
                new_excludes.append(route[key])

    set_session(
        phone,
        etat="itineraire_actif",
        ligne=result["routes"][0].get("number") or result["routes"][0].get("number1"),
        destination=dest_query,
        signalement={"origin": origin_query, "dest": dest_query,
                     "exclude_lines": new_excludes}
    )

    fmt_fn = _FMT.get(lang, _FMT["fr"]).get(result["status"])
    if fmt_fn:
        return fmt_fn(result)

    return _not_found_fr(result) if lang == "fr" else _not_found_wo(result)