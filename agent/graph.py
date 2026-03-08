"""
agent/graph.py — Moteur itinéraire Sëtu
Source : dem_dikk_lines_gps_final.json (site officiel Dem Dikk · 39 lignes · 375 arrêts)

Utilise le même fichier que extractor.py — zéro duplication de données.
"""
import json
import os
from collections import defaultdict
from typing import Optional
from unicodedata import normalize as _unorm


# ── Chargement ────────────────────────────────────────────

def _load(path: str) -> dict:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    full = os.path.join(base, path)
    with open(full, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Normalisation ─────────────────────────────────────────

def _norm(s: str) -> str:
    s = _unorm("NFD", s.lower())
    s = "".join(c for c in s if ord(c) < 0x300 or ord(c) > 0x36F)
    s = s.replace("-", " ").replace("'", " ").replace(".", "")
    return " ".join(s.split())


# ── Alias populaires ──────────────────────────────────────

_ALIASES: dict[str, str] = {
    "leclerc":                  "terminus leclerc",
    "gare leclerc":             "terminus leclerc",
    "place leclerc":            "leclerc",
    "palais":                   "terminus palais 2",
    "palais 2":                 "terminus palais 2",
    "palais 1":                 "palais 1",
    "aeroport":                 "terminus aeroport lss",
    "aéroport":                 "terminus aeroport lss",
    "lss":                      "terminus aeroport lss",
    "liberte 6":                "terminus liberte 6",
    "liberté 6":                "terminus liberte 6",
    "liberte 5":                "terminus liberte 5",
    "liberté 5":                "terminus liberte 5 dieuppeul",
    "ouakam":                   "terminus ouakam",
    "parcelles":                "terminus des parcelles",
    "parcelles assainies":      "terminus des parcelles",
    "rufisque":                 "terminus rufisque",
    "gare rufisque":            "gare de rufisque",
    "sandaga":                  "sandaga",
    "colobane":                 "colobane",
    "ucad":                     "ucad",
    "independence":             "place de l independence",
    "indépendance":             "place de l independence",
    "place independance":       "place de l independence",
    "place de l independance":  "place de l independence",
    "guediawaye":               "terminus guediawaye",
    "guédiawaye":               "terminus guediawaye",
    "keur massar":              "croisement keur massar",
    "yoff":                     "yoff village",
    "grand yoff":               "grand yoff",
    "hlm":                      "hlm grand yoff",
    "malika":                   "terminus malika",
    "daroukhane":               "gare routiere daroukhane",
    "mbao":                     "fass mbao",
}


# ── Graphe ────────────────────────────────────────────────

class DemDikkGraph:
    def __init__(self, data: dict):
        self.stop_to_lines: dict[str, list[str]] = defaultdict(list)
        self.line_stops:    dict[str, list[str]] = {}
        self.line_meta:     dict[str, dict]      = {}
        self.canon_to_raw:  dict[str, str]       = {}
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
                for raw in line["stops"]:
                    raw = raw.strip()
                    c   = _norm(raw)
                    canon_stops.append(c)
                    if c not in self.canon_to_raw:
                        self.canon_to_raw[c] = raw
                    if num not in self.stop_to_lines[c]:
                        self.stop_to_lines[c].append(num)
                self.line_stops[num] = canon_stops

    def find_stop(self, query: str) -> Optional[str]:
        q = _norm(query)
        if q in _ALIASES:
            target     = _norm(_ALIASES[q])
            if target in self.stop_to_lines:
                return target
            candidates = [s for s in self.stop_to_lines if target in s]
            if candidates:
                return sorted(candidates, key=len)[0]
        if q in self.stop_to_lines:
            return q
        candidates = [s for s in self.stop_to_lines if q in s]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return sorted(candidates, key=len)[0]
        words      = q.split()
        candidates = [s for s in self.stop_to_lines if all(w in s for w in words)]
        if candidates:
            return sorted(candidates, key=len)[0]
        return None

    def display(self, canon: str) -> str:
        return self.canon_to_raw.get(canon, canon).title()

    def direct(self, origin: str, dest: str) -> list[dict]:
        results = []
        for num, stops in self.line_stops.items():
            if origin in stops and dest in stops:
                i, j = stops.index(origin), stops.index(dest)
                seg  = stops[i:j+1] if i <= j else list(reversed(stops[j:i+1]))
                results.append({
                    "number":     num,
                    "name":       self.line_meta[num]["name"],
                    "terminus_a": self.line_meta[num]["terminus_a"],
                    "terminus_b": self.line_meta[num]["terminus_b"],
                    "stops":      [self.display(s) for s in seg],
                    "nb_stops":   len(seg) - 1,
                })
        return sorted(results, key=lambda x: x["nb_stops"])

    def with_transfer(self, origin: str, dest: str) -> list[dict]:
        results   = []
        seen_keys: set = set()
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
                    i1    = stops1.index(origin)
                    j1    = stops1.index(t)
                    i2    = stops2.index(t)
                    j2    = stops2.index(dest)
                    total = abs(j1 - i1) + abs(j2 - i2)
                    if best is None or total < best["nb_stops"]:
                        seg1 = stops1[i1:j1+1] if i1 <= j1 else list(reversed(stops1[j1:i1+1]))
                        seg2 = stops2[i2:j2+1] if i2 <= j2 else list(reversed(stops2[j2:i2+1]))
                        best = {
                            "number1":  l1,
                            "name1":    self.line_meta[l1]["name"],
                            "stops1":   [self.display(s) for s in seg1],
                            "transfer": self.display(t),
                            "number2":  l2,
                            "name2":    self.line_meta[l2]["name"],
                            "stops2":   [self.display(s) for s in seg2],
                            "nb_stops": total,
                        }
                if best:
                    key = (best["number1"], best["number2"], best["transfer"])
                    if key not in seen_keys:
                        seen_keys.add(key)
                        results.append(best)
        return sorted(results, key=lambda x: x["nb_stops"])[:3]

    def find_route(self, origin_query: str, dest_query: str) -> dict:
        origin = self.find_stop(origin_query)
        dest   = self.find_stop(dest_query)
        if not origin:
            return {"status": "stop_not_found", "which": "origin", "query": origin_query}
        if not dest:
            return {"status": "stop_not_found", "which": "dest",   "query": dest_query}
        if origin == dest:
            return {"status": "same_stop", "stop": self.display(origin)}
        directs = self.direct(origin, dest)
        if directs:
            return {
                "status":         "direct",
                "origin_display": self.display(origin),
                "dest_display":   self.display(dest),
                "routes":         directs,
            }
        transfers = self.with_transfer(origin, dest)
        if transfers:
            return {
                "status":         "transfer",
                "origin_display": self.display(origin),
                "dest_display":   self.display(dest),
                "routes":         transfers,
            }
        return {
            "status":         "not_found",
            "origin_display": self.display(origin),
            "dest_display":   self.display(dest),
        }


# ── Singleton ─────────────────────────────────────────────

_graph: Optional[DemDikkGraph] = None

def get_graph(json_path: str = "dem_dikk_lines_gps_final.json") -> DemDikkGraph:
    global _graph
    if _graph is None:
        data   = _load(json_path)
        _graph = DemDikkGraph(data)
    return _graph