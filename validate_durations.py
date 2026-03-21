#!/usr/bin/env python3
"""
validate_durations.py — Xëtu V8.2
Validation et correction des temps_vers_suivant_sec dans routes_geometry_v13.json.

Sources GTFS fiables (NE PAS TOUCHER) :
  - L1  : 45 arrêts, 46s–266s
  - L4  : 33 arrêts, 22s–347s

Usage :
  python validate_durations.py routes_geometry_v13.json
  python validate_durations.py routes_geometry_v13.json --fix
"""

import json
import sys
import argparse
import statistics
from pathlib import Path
from typing import Optional

# ── Seuils ────────────────────────────────────────────────
MIN_SEG_S       = 20      # < 20s → aberrant (bus téléporteur)
MAX_SEG_S       = 600     # > 600s → aberrant (10 min entre 2 arrêts = probablement concat aller+retour)
MIN_TOTAL_S     = 600     # trajet < 10 min → suspect
MAX_TOTAL_S     = 10800   # trajet > 3h  → suspect
MAX_LONG_SEGS   = 2       # > 2 segments > 600s → symptôme aller+retour concaténés
FALLBACK_S      = 120     # valeur par défaut si interpolation impossible

# Lignes GTFS — exemptions fixes
GTFS_LINES = {"L1", "L4", "1", "4"}


# ══════════════════════════════════════════════════════════
# CHARGEMENT
# ══════════════════════════════════════════════════════════

def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_lines(data: dict) -> list[tuple[str, dict]]:
    """
    Retourne [(ligne_id, ligne_data), ...]
    Compatible avec les deux racines possibles : "routes" ou "lignes".
    """
    root = data.get("routes") or data.get("lignes") or {}
    return list(root.items())


def get_arrets(ligne_data: dict) -> list[dict]:
    """Retourne la liste des arrêts (clé 'arrets' ou 'stops')."""
    return ligne_data.get("arrets") or ligne_data.get("stops") or []


# ══════════════════════════════════════════════════════════
# ANALYSE
# ══════════════════════════════════════════════════════════

def analyse_ligne(ligne_id: str, ligne_data: dict) -> dict:
    """
    Analyse une ligne et retourne un dict de résultats.
    Le dernier arrêt n'a pas de 'temps_vers_suivant_sec' (None est normal).
    """
    arrets = get_arrets(ligne_data)
    n = len(arrets)

    # Segments = tous sauf le dernier (qui n'a pas de suivant)
    segments: list[tuple[int, str, Optional[int]]] = []
    for i, arret in enumerate(arrets[:-1]):
        t = arret.get("temps_vers_suivant_sec")
        nom = arret.get("nom", arret.get("name", f"Arrêt #{i}"))
        segments.append((i, nom, t))

    # Valeurs numériques uniquement (ignore None)
    valeurs = [t for _, _, t in segments if t is not None]

    if not valeurs:
        return {
            "id": ligne_id,
            "nom": ligne_data.get("nom") or ligne_data.get("name", ""),
            "nb_arrets": n,
            "total_s": None,
            "min_s": None,
            "max_s": None,
            "mean_s": None,
            "aberrants": [],
            "longs_segs": [],
            "suspect": True,
            "raison": "Aucun temps_vers_suivant_sec trouvé",
        }

    total_s = sum(valeurs)
    min_s   = min(valeurs)
    max_s   = max(valeurs)
    mean_s  = statistics.mean(valeurs)

    # Segments aberrants
    aberrants = [
        {"idx": i, "nom": nom, "valeur_s": t,
         "type": "trop_court" if t < MIN_SEG_S else "trop_long"}
        for i, nom, t in segments
        if t is not None and (t < MIN_SEG_S or t > MAX_SEG_S)
    ]

    # Segments > MAX_SEG_S (symptôme aller+retour)
    longs_segs = [s for s in aberrants if s["type"] == "trop_long"]

    # Diagnostics suspects
    raisons = []
    if total_s < MIN_TOTAL_S:
        raisons.append(f"trajet total {_fmt_dur(total_s)} < 10 min")
    if total_s > MAX_TOTAL_S:
        raisons.append(f"trajet total {_fmt_dur(total_s)} > 3h")
    if len(longs_segs) > MAX_LONG_SEGS:
        raisons.append(f"{len(longs_segs)} segments > 600s (probable concat aller+retour)")

    return {
        "id": ligne_id,
        "nom": ligne_data.get("nom") or ligne_data.get("name", ""),
        "nb_arrets": n,
        "total_s": total_s,
        "min_s": min_s,
        "max_s": max_s,
        "mean_s": round(mean_s, 1),
        "aberrants": aberrants,
        "longs_segs": longs_segs,
        "suspect": bool(raisons),
        "raison": " | ".join(raisons) if raisons else "",
    }


# ══════════════════════════════════════════════════════════
# FORMATAGE
# ══════════════════════════════════════════════════════════

def _fmt_dur(s: Optional[int]) -> str:
    if s is None:
        return "N/A"
    h, rem = divmod(int(s), 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{sec:02d}s"
    if m:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


def _fmt_seg(seg: dict) -> str:
    t = seg["valeur_s"]
    flag = "⚠️ COURT" if seg["type"] == "trop_court" else "🔴 LONG"
    return f"    [{seg['idx']:3d}] {seg['nom'][:40]:<40} → {t}s  {flag}"


def _fix_advice(res: dict) -> str:
    """Proposition de correction textuelle pour une ligne suspecte."""
    if not res["suspect"] and not res["aberrants"]:
        return ""
    parts = []
    nb_ab = len(res["aberrants"])
    nb_lo = len(res["longs_segs"])
    if nb_lo > MAX_LONG_SEGS:
        parts.append(
            f"  → Probable concat aller+retour : couper à la moitié ({res['nb_arrets']//2} arrêts) "
            f"et recalculer avec OSRM."
        )
    if nb_ab > 0:
        parts.append(
            f"  → {nb_ab} segment(s) aberrant(s) : remplacer par interpolation linéaire "
            f"entre voisins valides (voir --fix)."
        )
    if res["total_s"] is not None and res["total_s"] < MIN_TOTAL_S:
        parts.append(
            f"  → Trajet trop court : vérifier si la ligne est un tronçon ou un navette."
        )
    return "\n".join(parts)


# ══════════════════════════════════════════════════════════
# RAPPORT
# ══════════════════════════════════════════════════════════

def print_report(results: list[dict]) -> None:
    ok      = [r for r in results if not r["suspect"] and not r["aberrants"]]
    warning = [r for r in results if r["aberrants"] and not r["suspect"]]
    suspect = [r for r in results if r["suspect"]]

    sep = "─" * 72

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║          XËTU — Validation routes_geometry_v13.json                ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"  {len(results)} lignes analysées  |  ✅ {len(ok)} OK  |  ⚠️ {len(warning)} warnings  |  🔴 {len(suspect)} suspects")
    print()

    # ── LIGNES OK ─────────────────────────────────────────
    print("━━━  LIGNES OK  " + "━" * 56)
    for r in sorted(ok, key=lambda x: x["id"]):
        gtfs = " [GTFS]" if r["id"].upper() in GTFS_LINES else ""
        print(
            f"  {r['id']:>6}  {r['nom'][:30]:<30}  "
            f"{r['nb_arrets']:3d} arrêts  "
            f"durée {_fmt_dur(r['total_s'])}  "
            f"moy {_fmt_dur(int(r['mean_s']) if r['mean_s'] else None)}/seg"
            f"{gtfs}"
        )

    # ── LIGNES AVEC SEGMENTS ABERRANTS (mais durée totale OK) ─
    if warning:
        print()
        print("━━━  SEGMENTS ABERRANTS (durée totale plausible)  " + "━" * 22)
        for r in sorted(warning, key=lambda x: x["id"]):
            print(sep)
            print(
                f"  ⚠️  Ligne {r['id']}  |  {r['nom']}  |  "
                f"{r['nb_arrets']} arrêts  |  durée {_fmt_dur(r['total_s'])}"
            )
            print(f"      min={r['min_s']}s  max={r['max_s']}s  moy={r['mean_s']}s")
            for ab in r["aberrants"]:
                print(_fmt_seg(ab))
            advice = _fix_advice(r)
            if advice:
                print(advice)

    # ── LIGNES SUSPECTES ──────────────────────────────────
    if suspect:
        print()
        print("━━━  LIGNES SUSPECTES  " + "━" * 49)
        for r in sorted(suspect, key=lambda x: x["id"]):
            print(sep)
            print(
                f"  🔴 Ligne {r['id']}  |  {r['nom']}  |  "
                f"{r['nb_arrets']} arrêts  |  durée {_fmt_dur(r['total_s'])}"
            )
            print(f"      Raison : {r['raison']}")
            if r["min_s"] is not None:
                print(f"      min={r['min_s']}s  max={r['max_s']}s  moy={r['mean_s']}s")
            if r["aberrants"]:
                print(f"      Segments aberrants ({len(r['aberrants'])}) :")
                for ab in r["aberrants"]:
                    print(_fmt_seg(ab))
            advice = _fix_advice(r)
            if advice:
                print(advice)

    print(sep)
    print()


# ══════════════════════════════════════════════════════════
# FIX — INTERPOLATION LINÉAIRE
# ══════════════════════════════════════════════════════════

def _interpolate_times(arrets: list[dict], ligne_id: str) -> tuple[list[dict], int]:
    """
    Remplace les temps aberrants (None inclus) par interpolation linéaire
    entre les voisins valides les plus proches.
    Retourne (arrets_corrigés, nb_corrections).
    """
    n = len(arrets)
    times = [a.get("temps_vers_suivant_sec") for a in arrets]
    # Dernier arrêt n'a pas de suivant — on l'ignore
    fixed = list(times)
    nb_fix = 0

    def is_bad(t) -> bool:
        return t is None or t < MIN_SEG_S or t > MAX_SEG_S

    # Identification des indices à corriger (sauf dernier)
    bad_indices = [i for i in range(n - 1) if is_bad(fixed[i])]

    for idx in bad_indices:
        # Chercher voisin gauche valide
        left_val, left_dist = None, 0
        for k in range(idx - 1, -1, -1):
            if k == n - 1:  # dernier arrêt → pas de temps
                continue
            if not is_bad(fixed[k]):
                left_val = fixed[k]
                left_dist = idx - k
                break

        # Chercher voisin droit valide
        right_val, right_dist = None, 0
        for k in range(idx + 1, n - 1):
            if not is_bad(fixed[k]):
                right_val = fixed[k]
                right_dist = k - idx
                break

        if left_val is not None and right_val is not None:
            # Interpolation pondérée par distance
            total_dist = left_dist + right_dist
            interp = round(
                (left_val * right_dist + right_val * left_dist) / total_dist
            )
        elif left_val is not None:
            interp = left_val
        elif right_val is not None:
            interp = right_val
        else:
            interp = FALLBACK_S

        # Clamp pour éviter de générer de nouveaux aberrants
        interp = max(MIN_SEG_S, min(interp, MAX_SEG_S))
        fixed[idx] = interp
        nb_fix += 1

    # Reconstruire les arrêts
    new_arrets = []
    for i, arret in enumerate(arrets):
        a = dict(arret)
        if i < n - 1:
            a["temps_vers_suivant_sec"] = fixed[i]
        new_arrets.append(a)

    return new_arrets, nb_fix


def apply_fixes(data: dict, results: list[dict]) -> tuple[dict, dict]:
    """
    Génère une copie du JSON avec les temps aberrants corrigés.
    Ne touche PAS aux lignes GTFS (L1, L4).
    Retourne (data_fixed, stats_par_ligne).
    """
    import copy
    data_fixed = copy.deepcopy(data)
    root_key = "routes" if "routes" in data_fixed else "lignes"
    root = data_fixed[root_key]

    stats = {}  # ligne_id → nb_corrections

    lines_with_issues = {
        r["id"] for r in results
        if r["aberrants"] or r["suspect"]
    }

    for ligne_id, ligne_data in root.items():
        # Exemption GTFS
        if ligne_id.upper() in GTFS_LINES or ligne_id in GTFS_LINES:
            stats[ligne_id] = {"skipped": True, "raison": "GTFS — exemption"}
            continue

        if ligne_id not in lines_with_issues:
            continue

        arrets_key = "arrets" if "arrets" in ligne_data else "stops"
        arrets = ligne_data.get(arrets_key, [])
        if not arrets:
            continue

        new_arrets, nb_fix = _interpolate_times(arrets, ligne_id)
        root[ligne_id][arrets_key] = new_arrets
        stats[ligne_id] = {"nb_corrections": nb_fix}

    return data_fixed, stats


def print_fix_summary(stats: dict) -> None:
    print()
    print("━━━  RÉSUMÉ --fix  " + "━" * 53)
    total_fix = 0
    for ligne_id, info in sorted(stats.items()):
        if info.get("skipped"):
            print(f"  {ligne_id:>6}  ⏭️  {info['raison']}")
        else:
            n = info["nb_corrections"]
            total_fix += n
            print(f"  {ligne_id:>6}  ✅  {n} segment(s) corrigé(s)")
    print(f"\n  Total corrections : {total_fix} segments")
    print()


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Validation des durées routes_geometry_v13.json — Xëtu"
    )
    parser.add_argument("json_path", help="Chemin vers routes_geometry_v13.json")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Génère routes_geometry_v13_fixed.json avec les temps corrigés",
    )
    args = parser.parse_args()

    path = Path(args.json_path)
    if not path.exists():
        print(f"❌ Fichier introuvable : {path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n📂 Chargement : {path} ({path.stat().st_size // 1024} KB)...")
    data = load_json(str(path))
    lines = iter_lines(data)
    print(f"   {len(lines)} lignes trouvées\n")

    # ── Analyse ───────────────────────────────────────────
    results = []
    for ligne_id, ligne_data in lines:
        results.append(analyse_ligne(ligne_id, ligne_data))

    # ── Rapport ───────────────────────────────────────────
    print_report(results)

    # ── Statistiques globales ─────────────────────────────
    all_totals = [r["total_s"] for r in results if r["total_s"] is not None]
    total_aberrants = sum(len(r["aberrants"]) for r in results)
    print(f"  Statistiques globales :")
    print(f"    Durée totale médiane  : {_fmt_dur(int(statistics.median(all_totals))) if all_totals else 'N/A'}")
    print(f"    Segments aberrants    : {total_aberrants}")
    print(f"    Lignes suspectes      : {sum(1 for r in results if r['suspect'])}")
    print(f"    Lignes OK             : {sum(1 for r in results if not r['suspect'] and not r['aberrants'])}")
    print()

    # ── Fix ───────────────────────────────────────────────
    if args.fix:
        print("🔧 Application des corrections (interpolation linéaire)...")
        data_fixed, stats = apply_fixes(data, results)
        out_path = path.parent / (path.stem + "_fixed.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data_fixed, f, ensure_ascii=False, indent=2)
        print_fix_summary(stats)
        print(f"✅ Fichier généré : {out_path}")
        print(f"   Taille : {out_path.stat().st_size // 1024} KB\n")
        print("⚠️  Lignes L1 et L4 non touchées (source GTFS fiable).")
        print()


if __name__ == "__main__":
    main()