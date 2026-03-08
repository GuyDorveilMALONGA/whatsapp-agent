"""
skills/itineraire.py — Skill itinéraire Sëtu
Extrait origin/dest depuis le message, calcule et formate l'itinéraire.
Source réseau : dem_dikk_lines.json (site officiel Dem Dikk · 39 lignes)
"""
import re
import logging
from agent.graph import get_graph

logger = logging.getLogger(__name__)

# ~2 min par arrêt moyenne (trafic Dakar inclus)
_MINS_PAR_ARRET = 2


def _duree(nb_stops: int) -> str:
    m = nb_stops * _MINS_PAR_ARRET
    if m < 60:
        return f"~{m} min"
    h, r = divmod(m, 60)
    return f"~{h}h{r:02d}" if r else f"~{h}h"


# ── Extraction origin/dest depuis le message ──────────────

# Patterns pour détecter "de X à Y", "depuis X vers Y", "X → Y"
_PATTERNS = [
    # "comment aller de X à Y", "je veux aller de X à Y"
    r'(?:de|depuis)\s+(.+?)\s+(?:à|au|vers|jusqu[aà]|pour)\s+(.+?)(?:\s*[?!.]|$)',
    # "je suis à X je vais à Y"
    r'(?:je\s+(?:suis|me\s+trouve)\s+(?:à|au))\s+(.+?)\s+(?:et\s+)?(?:je\s+vais|je\s+veux\s+aller|je\s+veux\s+me\s+rendre)\s+(?:à|au|vers)?\s*(.+?)(?:\s*[?!.]|$)',
    # "X → Y" ou "X -> Y"
    r'(.+?)\s*(?:→|->|➔)\s*(.+?)(?:\s*[?!.]|$)',
    # "quel bus pour X depuis Y" / "quel bus pour aller à X"
    r'(?:quel\s+bus\s+(?:pour|pour\s+aller\s+[aà])|comment\s+aller\s+[aà])\s+(.+?)(?:\s+depuis\s+(.+?))?(?:\s*[?!.]|$)',
    # Wolof : "dem ci X, mangi X"
    r'(?:dem\s+(?:ci|fa))\s+(.+?)(?:\s+ci\s+(.+?))?(?:\s*[?!.]|$)',
]


def _extract_od(message: str) -> tuple[str | None, str | None]:
    """
    Extrait (origin, destination) depuis le message.
    Retourne (None, dest) si seule la destination est trouvée.
    """
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
        f"🚌 *Ligne {best['number']}*",
        f"De *{r['origin_display']}* → *{r['dest_display']}*",
        f"Durée : {_duree(best['nb_stops'])} · {best['nb_stops']} arrêts",
    ]
    if other:
        alts = " · ".join(f"Ligne {x['number']}" for x in other[:2])
        lines.append(f"_Aussi : {alts}_")
    return "\n".join(lines)


def _transfer_fr(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚌 *Ligne {best['number1']}* depuis *{r['origin_display']}*",
        f"↳ Descends à *{best['transfer']}* (correspondance)",
        f"🚌 *Ligne {best['number2']}* jusqu'à *{r['dest_display']}*",
        f"Durée : {_duree(best['nb_stops'])} · {best['nb_stops']} arrêts au total",
    ])


def _not_found_fr(r: dict) -> str:
    return (
        f"❌ Aucun trajet trouvé entre *{r['origin_display']}* "
        f"et *{r['dest_display']}* avec une correspondance max.\n"
        "Essaie Yango pour ce trajet. 🚗"
    )


def _stop_not_found_fr(r: dict) -> str:
    which = "départ" if r["which"] == "origin" else "destination"
    return (
        f"❓ Je ne connais pas *{r['query']}* comme arrêt de {which}.\n"
        "Essaie : _Terminus Leclerc · Palais 2 · Yoff Village · Sandaga · UCAD_"
    )


def _no_od_fr() -> str:
    return (
        "Pour un itinéraire, dis-moi d'où et où tu vas. Exemple :\n"
        "_Yoff → Sandaga_\n"
        "_Comment aller de Parcelles à UCAD ?_"
    )


def _ask_origin_fr(dest: str) -> str:
    return f"Tu veux aller à *{dest}* — tu es à quel arrêt en ce moment ?"


# ── Formatage Wolof ───────────────────────────────────────

def _direct_wo(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚌 *Ligne {best['number']}* la jëf.",
        f"Dëkk ci *{r['origin_display']}*, dem *{r['dest_display']}*.",
        f"Jamm : {_duree(best['nb_stops'])} · {best['nb_stops']} areet.",
    ])


def _transfer_wo(r: dict) -> str:
    best = r["routes"][0]
    return "\n".join([
        f"🚌 Jël *Ligne {best['number1']}* ci *{r['origin_display']}*.",
        f"↳ Surfu ci *{best['transfer']}*.",
        f"🚌 Jël *Ligne {best['number2']}*, dem *{r['dest_display']}*.",
        f"Jamm : {_duree(best['nb_stops'])}.",
    ])


def _not_found_wo(r: dict) -> str:
    return (
        f"❌ Amul yoon bi ci *{r['origin_display']}* ñëw *{r['dest_display']}*.\n"
        "Jël taxi Yango. 🚗"
    )


# ── Table de dispatch ─────────────────────────────────────

_FMT = {
    "fr": {
        "direct":         _direct_fr,
        "transfer":       _transfer_fr,
        "not_found":      _not_found_fr,
        "stop_not_found": _stop_not_found_fr,
        "same_stop":      lambda r: f"Tu es déjà à *{r['stop']}* 😄",
    },
    "wo": {
        "direct":         _direct_wo,
        "transfer":       _transfer_wo,
        "not_found":      _not_found_wo,
        "stop_not_found": _stop_not_found_fr,
        "same_stop":      lambda r: f"Dëkk nga fi ci *{r['stop']}* 😄",
    },
}


# ── Point d'entrée principal ──────────────────────────────

async def handle(message: str, contact: dict, langue: str) -> str:
    """
    Appelé depuis main.py quand intent == "itineraire".
    Extrait origin/dest, calcule, formate.
    """
    lang  = langue if langue in _FMT else "fr"
    graph = get_graph()

    origin_query, dest_query = _extract_od(message)

    # Pas de destination détectée
    if not dest_query:
        return _no_od_fr() if lang == "fr" else (
            "Wax ma fi nga dëkk ak fa nga dem. Xeeti : _Yoff → Sandaga_"
        )

    # Pas d'origine — on la demande (flow multi-tour possible en V2)
    if not origin_query:
        dest_display = dest_query.title()
        return _ask_origin_fr(dest_display) if lang == "fr" else (
            f"Fa nga dem *{dest_display}* — fi nga dëkk ?"
        )

    result = graph.find_route(origin_query, dest_query)

    fmt_table = _FMT.get(lang, _FMT["fr"])
    fmt_fn    = fmt_table.get(result["status"])

    if fmt_fn:
        return fmt_fn(result)

    logger.error(f"[Itinéraire] Status inconnu: {result['status']}")
    return _not_found_fr(result) if lang == "fr" else _not_found_wo(result)
