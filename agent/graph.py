"""
agent/graph.py — V3.2 Walk-Aware Routing
Source : core.network (singleton JSON — plus de _load() local)

V3.2 vs V3.1 :
  - _load() supprimé → DemDikkGraph reçoit le dict directement depuis core.network
  - get_graph() utilise core.network._RAW (déjà en mémoire, zéro I/O)
  - Tout le reste inchangé (5 passes fuzzy, Walk-Aware, Haversine)
"""
import math
import logging
from collections import defaultdict
from difflib import get_close_matches, SequenceMatcher
from typing import Optional
from unicodedata import normalize as _unorm

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────

_WALK_SPEED_MS    = 1.3
_SECS_PER_STOP    = 120
_TRANSFER_PENALTY = 360
_RADIUS_MAX_M     = 900
_RADIUS_ZONES     = [200, 500, 900]

_CUTOFF_HIGH = 0.6
_CUTOFF_LOW  = 0.4


# ── Normalisation ─────────────────────────────────────────

def _norm(s: str) -> str:
    s = _unorm("NFD", s.lower())
    s = "".join(c for c in s if ord(c) < 0x300 or ord(c) > 0x36F)
    s = s.replace("-", " ").replace("'", " ").replace(".", "")
    return " ".join(s.split())


def _norm_ascii(s: str) -> str:
    s = _unorm("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = s.lower().replace("-", " ").replace("'", " ").replace(".", "")
    return " ".join(s.split())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ── Haversine ─────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) *
         math.sin((lon2 - lon1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _walk_time(dist_m: float) -> float:  return dist_m / _WALK_SPEED_MS
def _walk_min(dist_m: float) -> int:     return max(1, round(_walk_time(dist_m) / 60))
def _bus_time(nb_stops: int) -> float:   return nb_stops * _SECS_PER_STOP
def _total_min(score_secs: float) -> int: return max(1, round(score_secs / 60))


# ── Alias populaires ──────────────────────────────────────

_ALIASES: dict[str, str] = {
    "leclerc":                 "terminus leclerc",
    "gare leclerc":            "terminus leclerc",
    "palais":                  "terminus palais 2",
    "palais 2":                "terminus palais 2",
    "palais 1":                "palais 1",
    "aeroport":                "terminus aeroport lss",
    "lss":                     "terminus aeroport lss",
    "liberte 6":               "terminus liberte 6",
    "liberte 5":               "terminus liberte 5",
    "ouakam":                  "terminus ouakam",
    "parcelles":               "terminus des parcelles",
    "parcelles assainies":     "terminus des parcelles",
    "rufisque":                "terminus rufisque",
    "gare rufisque":           "gare de rufisque",
    "sandaga":                 "sandaga",
    "colobane":                "colobane",
    "ucad":                    "ucad",
    "independence":            "place de l independence",
    "independance":            "place de l independence",
    "place independance":      "place de l independence",
    "place de l independance": "place de l independence",
    "guediawaye":              "terminus guediawaye",
    "keur massar":             "croisement keur massar",
    "yoff":                    "yoff village",
    "rond point yoff":         "yoff village",
    "rp yoff":                 "yoff village",
    "grand yoff":              "grand yoff",
    "hlm":                     "hlm grand yoff",
    "malika":                  "terminus malika",
    "daroukhane":              "gare routiere daroukhane",
    "mbao":                    "fass mbao",
    "medina":                  "medina",
    "plateau":                 "plateau",
    "petersen":                "petersen",
    "tilene":                  "tilene",
    "pompiers":                "pompiers",
    "castor":                  "castor",
    "camberene":               "camberene",
    "niary tally":             "niary tally",
    "point e":                 "point e",
    "pikine":                  "pikine",
    "thiaroye":                "thiaroye",
}


# ── Graphe ────────────────────────────────────────────────

class DemDikkGraph:
    def __init__(self, data: dict):
        self.stop_to_lines:   dict[str, list[str]]           = defaultdict(list)
        self.line_stops:      dict[str, list[str]]           = {}
        self.line_meta:       dict[str, dict]                = {}
        self.canon_to_raw:    dict[str, str]                 = {}
        self.stop_coords:     dict[str, tuple[float, float]] = {}
        self._all_stops:      list[str]                      = []
        self._ascii_to_canon: dict[str, str]                 = {}
        self._build(data)

    def _build(self, data: dict):
        for category, lines in data["categories"].items():
            for line in lines:
                num = line["number"]
                self.line_meta[num] = {
                    "number":     num,
                    "name":       line["name"],
                    "category":   line["category"],
                    "terminus_a": line["terminus_a"],
                    "terminus_b": line["terminus_b"],
                }
                canon_stops = []
                for stop in line["stops"]:
                    raw = stop["nom"].strip()
                    c   = _norm(raw)
                    canon_stops.append(c)
                    if c not in self.canon_to_raw:
                        self.canon_to_raw[c] = raw
                    if c not in self.stop_coords and stop.get("lat") and stop.get("lon"):
                        self.stop_coords[c] = (stop["lat"], stop["lon"])
                    if num not in self.stop_to_lines[c]:
                        self.stop_to_lines[c].append(num)
                self.line_stops[num] = canon_stops

        self._all_stops = list(self.stop_to_lines.keys())
        for canon in self._all_stops:
            ascii_key = _norm_ascii(canon)
            if ascii_key not in self._ascii_to_canon:
                self._ascii_to_canon[ascii_key] = canon

        logger.info(
            f"[Graph] {len(self.line_stops)} lignes · "
            f"{len(self._all_stops)} arrêts · "
            f"{len(self._ascii_to_canon)} clés ASCII"
        )

    def find_stop(self, query: str) -> Optional[str]:
        if not query or not query.strip():
            return None

        q_norm  = _norm(query)
        q_ascii = _norm_ascii(query)

        # Passe 1 : alias exact
        if q_ascii in _ALIASES:
            target = _norm_ascii(_ALIASES[q_ascii])
            canon  = self._ascii_to_canon.get(target)
            if canon:
                return canon
            candidates = [c for a, c in self._ascii_to_canon.items() if a.startswith(target)]
            if candidates:
                return max(candidates, key=lambda c: _similarity(q_ascii, _norm_ascii(c)))

        # Passe 2 : exact _norm
        if q_norm in self.stop_to_lines:
            return q_norm

        # Passe 3 : exact ASCII
        if q_ascii in self._ascii_to_canon:
            return self._ascii_to_canon[q_ascii]

        # Passe 4 : substring avec meilleur score
        subs = [c for c in self.stop_to_lines
                if q_ascii in _norm_ascii(c) or _norm_ascii(c) in q_ascii]
        if subs:
            return max(subs, key=lambda c: _similarity(q_ascii, _norm_ascii(c)))

        # Passe 5 : difflib fuzzy
        ascii_keys = list(self._ascii_to_canon.keys())
        matches = get_close_matches(q_ascii, ascii_keys, n=3, cutoff=_CUTOFF_HIGH)
        if not matches:
            matches = get_close_matches(q_ascii, ascii_keys, n=3, cutoff=_CUTOFF_LOW)
        if matches:
            best_ascii = max(matches, key=lambda a: _similarity(q_ascii, a))
            return self._ascii_to_canon[best_ascii]

        # Passe 6 : mots-clés
        words = q_ascii.split()
        if len(words) >= 2:
            kw = [c for c in self.stop_to_lines
                  if all(w in _norm_ascii(c) for w in words)]
            if kw:
                return max(kw, key=lambda c: _similarity(q_ascii, _norm_ascii(c)))

        logger.warning(f"[find_stop] INTROUVABLE '{query}'")
        return None

    def display(self, canon: str) -> str:
        return self.canon_to_raw.get(canon, canon).title()

    def find_stops_nearby(self, lat: float, lon: float,
                          radius_m: float = _RADIUS_MAX_M) -> list[dict]:
        results = []
        for canon, (slat, slon) in self.stop_coords.items():
            dist = haversine(lat, lon, slat, slon)
            if dist <= radius_m:
                zone = next((z for z in _RADIUS_ZONES if dist <= z), _RADIUS_MAX_M)
                results.append({
                    "canon":   canon,
                    "display": self.display(canon),
                    "dist_m":  dist,
                    "zone":    zone,
                })
        return sorted(results, key=lambda x: x["dist_m"])

    def _segment(self, stops, a, b):
        i, j = stops.index(a), stops.index(b)
        return stops[i:j+1] if i <= j else list(reversed(stops[j:i+1]))

    def direct(self, origin: str, dest: str) -> list[dict]:
        results = []
        for num, stops in self.line_stops.items():
            if origin in stops and dest in stops:
                seg = self._segment(stops, origin, dest)
                nb  = len(seg) - 1
                results.append({
                    "number":     num,
                    "name":       self.line_meta[num]["name"],
                    "terminus_a": self.line_meta[num]["terminus_a"],
                    "terminus_b": self.line_meta[num]["terminus_b"],
                    "stops":      [self.display(s) for s in seg],
                    "nb_stops":   nb,
                    "score":      _bus_time(nb),
                })
        return sorted(results, key=lambda x: x["score"])

    def walk_to_direct(self, origin: str, dest: str) -> list[dict]:
        coords = self.stop_coords.get(origin)
        if not coords:
            return []
        lat, lon    = coords
        nearby      = self.find_stops_nearby(lat, lon, _RADIUS_MAX_M)
        dest_coords = self.stop_coords.get(dest)
        results, seen = [], set()

        for near in nearby:
            walk_stop = near["canon"]
            if walk_stop == origin:
                continue
            dist_m    = near["dist_m"]
            walk_secs = _walk_time(dist_m)

            for num, stops in self.line_stops.items():
                if walk_stop not in stops or dest not in stops:
                    continue
                seg      = self._segment(stops, walk_stop, dest)
                nb       = len(seg) - 1
                bus_secs = _bus_time(nb)
                walk_dest_m, walk_dest_secs = 0, 0

                if dest_coords:
                    dlat, dlon = dest_coords
                    for stop_c, (slat, slon) in self.stop_coords.items():
                        if stop_c not in stops:
                            continue
                        d = haversine(dlat, dlon, slat, slon)
                        if 0 < d <= 500 and stop_c != dest:
                            alt_seg   = self._segment(stops, walk_stop, stop_c)
                            alt_nb    = len(alt_seg) - 1
                            alt_score = walk_secs + _bus_time(alt_nb) + _walk_time(d)
                            if alt_score < walk_secs + bus_secs:
                                seg, nb       = alt_seg, alt_nb
                                bus_secs      = _bus_time(nb)
                                walk_dest_m   = d
                                walk_dest_secs = _walk_time(d)

                total_score = walk_secs + bus_secs + walk_dest_secs
                key         = (num, walk_stop)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "number":        num,
                        "name":          self.line_meta[num]["name"],
                        "walk_stop":     self.display(walk_stop),
                        "walk_dist_m":   round(dist_m),
                        "walk_min":      _walk_min(dist_m),
                        "stops":         [self.display(s) for s in seg],
                        "nb_stops":      nb,
                        "walk_dest_m":   round(walk_dest_m),
                        "walk_dest_min": _walk_min(walk_dest_m) if walk_dest_m else 0,
                        "total_min":     _total_min(total_score),
                        "score":         total_score,
                        "zone":          near["zone"],
                    })

        return sorted(results, key=lambda x: x["score"])[:3]

    def with_transfer(self, origin: str, dest: str) -> list[dict]:
        results, seen_keys = [], set()

        for l1 in self.stop_to_lines.get(origin, []):
            stops1 = self.line_stops[l1]
            if origin not in stops1:
                continue
            set1 = set(stops1)

            for l2 in self.stop_to_lines.get(dest, []):
                if l1 == l2:
                    continue
                stops2 = self.line_stops[l2]
                if dest not in stops2:
                    continue
                common = [s for s in stops2 if s in set1]
                if not common:
                    continue

                best = None
                for t in common:
                    i1, j1 = stops1.index(origin), stops1.index(t)
                    i2, j2 = stops2.index(t),      stops2.index(dest)
                    nb     = abs(j1 - i1) + abs(j2 - i2)
                    score  = _bus_time(nb) + _TRANSFER_PENALTY
                    if best is None or score < best["score"]:
                        best = {
                            "number1":   l1,
                            "name1":     self.line_meta[l1]["name"],
                            "stops1":    [self.display(s) for s in self._segment(stops1, origin, t)],
                            "transfer":  self.display(t),
                            "number2":   l2,
                            "name2":     self.line_meta[l2]["name"],
                            "stops2":    [self.display(s) for s in self._segment(stops2, t, dest)],
                            "nb_stops":  nb,
                            "total_min": _total_min(score),
                            "score":     score,
                        }
                if best:
                    key = (best["number1"], best["number2"], best["transfer"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        results.append(best)

        return sorted(results, key=lambda x: x["score"])[:3]

    def find_route(self, origin_query: str, dest_query: str,
                   no_transfer: bool = False) -> dict:

        origin = self.find_stop(origin_query)
        dest   = self.find_stop(dest_query)

        if not origin:
            return {"status": "stop_not_found", "which": "origin", "query": origin_query}
        if not dest:
            return {"status": "stop_not_found", "which": "dest",   "query": dest_query}
        if origin == dest:
            return {"status": "same_stop", "stop": self.display(origin)}

        origin_display = self.display(origin)
        dest_display   = self.display(dest)

        logger.info(f"[find_route] '{origin_query}'→'{origin_display}' | '{dest_query}'→'{dest_display}'")

        directs = self.direct(origin, dest)
        if directs:
            return {"status": "direct", "origin_display": origin_display,
                    "dest_display": dest_display, "routes": directs}

        if no_transfer:
            wtd = self.walk_to_direct(origin, dest)
            if wtd:
                return {"status": "walk_direct", "origin_display": origin_display,
                        "dest_display": dest_display, "routes": wtd}
            return {"status": "no_transfer_not_found",
                    "origin_display": origin_display, "dest_display": dest_display}

        wtd       = self.walk_to_direct(origin, dest)
        transfers = self.with_transfer(origin, dest)

        best_wtd      = wtd[0]       if wtd       else None
        best_transfer = transfers[0] if transfers else None

        if best_wtd and best_transfer:
            if best_wtd["score"] <= best_transfer["score"]:
                return {"status": "walk_direct", "origin_display": origin_display,
                        "dest_display": dest_display, "routes": wtd,
                        "alt_transfer": best_transfer}
            return {"status": "transfer", "origin_display": origin_display,
                    "dest_display": dest_display, "routes": transfers, "alt_walk": best_wtd}

        if best_wtd:
            return {"status": "walk_direct", "origin_display": origin_display,
                    "dest_display": dest_display, "routes": wtd}
        if best_transfer:
            return {"status": "transfer", "origin_display": origin_display,
                    "dest_display": dest_display, "routes": transfers}

        return {"status": "not_found", "origin_display": origin_display,
                "dest_display": dest_display}


# ── Singleton — branché sur core.network ─────────────────

_graph: Optional[DemDikkGraph] = None

def get_graph() -> DemDikkGraph:
    global _graph
    if _graph is None:
        # Réutilise le dict déjà en mémoire depuis core.network
        # Zéro lecture disque supplémentaire
        from core.network import _RAW
        _graph = DemDikkGraph(_RAW)
    return _graph