"""
skills/itineraire.py — V3 Walk-Aware Routing
Calcule et formate les itinéraires avec le nouveau moteur Walk-Aware.

Statuts gérés :
  direct              → bus direct origin → dest
  walk_direct         → marche Xm + bus direct
  transfer            → correspondance classique
  no_transfer_not_found → aucun bus direct même en marchant
  not_found           → aucun trajet trouvé
  stop_not_found      → arrêt inconnu
  same_stop           → départ = arrivée
"""
import re
import logging
from agent.graph import get_graph
from core.session_manager import set_attente_origin, get_context, reset_context

logger = logging.getLogger(__name__)


# ── Détection mode no_transfer ────────────────────────────

_NO_TRANSFER_PATTERNS = [
    r"\b(sans\s+correspondance|sans\s+changer|direct\s+seulement|bus\s+direct)\b",
    r"\b(je\s+(ne\s+)?peux\s+pas\s+marcher|je\s+ne\s+veux\s+pas\s+marcher)\b",
    r"\b(direct\s+uniquement|uniquement\s+direct)\b",
]

def _is_no_transfer(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in _NO_TRANSFER_PATTERNS)


# ── Extraction origin/dest ────────────────────────────────

_PATTERNS = [
    r'(?:de|depuis)\s+(.+?)\s+(?:à|au|vers|jusqu[aà]|pour)\s+(.+?)(?:\s*[?!.]|$)',
    r'je\s+suis\s+(?:à|au)\s+(.+?)\s+(?:et\s+)?je\s+veux\s+(?:aller\s+)?(?:à|au|vers)?\s*(.+?)(?:\s*[?!.]|$)',
    r'je\s+me\s+trouve\s+(?:à|au)\s+(.+?)\s+(?:et\s+)?(?:je\s+vais|je\s+veux\s+aller)\s+(?:à|au|vers)?\s*(.+?)(?:\s*[?!.]|$)',
    r'(.+?)\s*(?:→|->|➔)\s*(.+?)(?:\s*[?!.]|$)',
    r'(?:quel\s+bus\s+(?:pour|pour\s+aller\s+[aà])|comment\s+aller\s+[aà])\s+(.+?)(?:\s+depuis\s+(.+?))?(?:\s*[?!.]|$)',
    r'(?:quelle\s+ligne|quel\s+bus)\s+(?:pour\s+(?:aller\s+)?(?:à|au)\s+)(.+?)(?:\s+depuis\s+(.+?))?(?:\s*[?!.]|$)',
    r'(?:dem\s+(?:ci|fa))\s+(.+?)(?:\s+ci\s+(.+?))?(?:\s*[?!.]|$)',
]

def _extract_od(message: str) -> tuple[str | None, str | None]:
    text = message.strip()
    for pattern in _PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            groups = [g.strip() for g in m.groups() if g and g.strip()]
            if len(groups) >= 2:
                return groups[0], groups[1]
            if len(groups) == 1:
                return None, groups[0]
    return None, None


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
        alts = " · ".join(f"Ligne {x['number']}" for x in other[:2])
        lines.append(f"_Aussi : {alts}_")
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
        lines.append(f"\n_Option B : Ligne {t['number1']} → Ligne {t['number2']} · ~{t['total_min']} min_")
    elif other:
        alts = " · ".join(f"Ligne {x['number']}" for x in other[:2])
        lines.append(f"\n_Aussi : {alts}_")

    lines.append("\n— *Xëtu*")
    return "\n".join(lines)


def _transfer_fr(r: dict) -> str:
    best  = r["routes"][0]
    lines = [
        f"🚌 *Ligne {best['number1']}* depuis *{r['origin_display']}*",
        f"↳ Descends à *{best['transfer']}* (correspondance)",
        f"🚌 *Ligne {best['number2']}* jusqu'à *{r['dest_display']}*",
        f"Total *~{best['total_min']} min*",
    ]
    if r.get("alt_walk"):
        w = r["alt_walk"]
        lines.append(
            f"\n_Option B : Marche {w['walk_min']} min → {w['walk_stop']} · Ligne {w['number']} · ~{w['total_min']} min_"
        )
    lines.append("\n— *Xëtu*")
    return "\n".join(lines)


def _not_found_fr(r: dict) -> str:
    return (
        f"❌ Aucun trajet trouvé entre *{r['origin_display']}* "
        f"et *{r['dest_display']}*.\n\n"
        "Essaie Yango pour ce trajet. 🚗\n\n"
        "— *Xëtu*"
    )


def _no_transfer_not_found_fr(r: dict) -> str:
    return (
        f"❌ Aucun bus direct entre *{r['origin_display']}* "
        f"et *{r['dest_display']}*, même en marchant un peu.\n\n"
        "Tu veux que je cherche avec une correspondance ?\n\n"
        "— *Xëtu*"
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
        "Exemple : _Yoff → Sandaga_ ou _Comment aller à UCAD ?_\n\n"
        "— *Xëtu*"
    )


def _ask_origin_fr(dest: str) -> str:
    return (
        f"Tu veux aller à *{dest}*.\n\n"
        "Tu es à quel arrêt en ce moment ?"
    )


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
        "Jël taxi Yango. 🚗\n\n"
        "— *Xëtu*"
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


# ── Point d'entrée principal ──────────────────────────────

async def handle(message: str, contact: dict, langue: str) -> str:
    lang        = langue if langue in _FMT else "fr"
    graph       = get_graph()
    no_transfer = _is_no_transfer(message)

    origin_query, dest_query = _extract_od(message)

    if not dest_query:
        return _no_od_fr() if lang == "fr" else (
            "Wax ma fi nga dëkk ak fa nga dem. Xeeti : _Yoff → Sandaga_\n\n— *Xëtu*"
        )

    if not origin_query:
        dest_display = dest_query.title()
        set_attente_origin(contact["phone"], dest_query)
        return _ask_origin_fr(dest_display) if lang == "fr" else (
            f"Fa nga dem *{dest_display}* — fi nga dëkk ?"
        )

    result = graph.find_route(origin_query, dest_query, no_transfer=no_transfer)
    fmt_fn = _FMT.get(lang, _FMT["fr"]).get(result["status"])

    if fmt_fn:
        return fmt_fn(result)

    logger.error(f"[Itinéraire] Status inconnu: {result['status']}")
    return _not_found_fr(result) if lang == "fr" else _not_found_wo(result)


# ── Flow multi-tour : réponse origine ────────────────────

async def handle_origin_response(phone: str, text: str, langue: str) -> str:
    """
    Appelé depuis main.py quand session est en état 'attente_origin'.
    L'usager vient de donner son arrêt de départ.
    """
    from agent.extractor import extract

    ctx         = get_context(phone)
    destination = ctx.destination

    reset_context(phone)

    if not destination:
        return _no_od_fr() if langue != "wo" else (
            "Wax ma fi nga dëkk ak fa nga dem. Xeeti : _Yoff → Sandaga_\n\n— *Xëtu*"
        )

    result_ext   = extract(text)
    origin_query = result_ext.arret_normalise or result_ext.arret or text.strip()
    lang         = langue if langue in _FMT else "fr"
    graph        = get_graph()
    no_transfer  = _is_no_transfer(text)
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
            "Jëfandikoo : _Liberté 6 · Sandaga · Yoff Village_\n\n"
            "— *Xëtu*"
        )

    fmt_fn = _FMT.get(lang, _FMT["fr"]).get(route_result["status"])
    if fmt_fn:
        return fmt_fn(route_result)

    return _not_found_fr(route_result) if lang == "fr" else _not_found_wo(route_result)