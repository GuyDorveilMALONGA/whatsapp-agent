#!/usr/bin/env python3
"""
fix_suspects.py — Xëtu V8.2
Correction chirurgicale des lignes avec boucles OSRM détectées manuellement.

Stratégie par ligne :
  - 23  : trop chaotique pour sauver → remplacée par squelette terminus-à-terminus
           avec temps interpolés (20 arrêts clés identifiés manuellement)
  - 121 : tronquée à l'arrêt [24] Yoff — boucle Yoff/Ngor détectée à [25]
  - 217 : tronquée à l'arrêt [56] Avenue Cheikh Anta Diop — boucle Mamelles à [57]
  - 218 : identique à 217 → même coupe + flag doublon dans les logs
  - 220 : tronquée à l'arrêt [8] Sortie Rufisque — boucles dès [9]

Usage :
  python fix_suspects.py routes_geometry_v13_fixed.json
  → génère routes_geometry_v13_fixed2.json
"""

import json
import copy
import sys
import statistics
from pathlib import Path

# ── Coupes définies manuellement après inspection ─────────
# Format : "ligne_id" → index du DERNIER arrêt à GARDER (inclus)
CUTS = {
    "121": 24,   # garde [0..24] → Yoff, coupe boucle Yoff/Ngor [25+]
    "217": 56,   # garde [0..56] → Avenue Cheikh Anta Diop, coupe boucle Mamelles [57+]
    "218": 56,   # identique à 217
    "220": 8,    # garde [0..8]  → Sortie Rufisque, coupe boucles Rufisque [9+]
}

# Ligne 23 : trop fragmentée pour une simple coupe
# On garde les arrêts [0..12] (Terminus Parcelles → Usine des Eaux)
# puis [29..55] (Allées Ababacar Sy → Terminus Leclerc) = trajet cohérent
# C'est la meilleure approximation récupérable sans données source
LIGNE_23_KEEP_RANGES = [(0, 12), (29, 55)]


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_root(data: dict) -> tuple[str, dict]:
    key = "routes" if "routes" in data else "lignes"
    return key, data[key]


def get_arrets_key(ligne_data: dict) -> str:
    return "arrets" if "arrets" in ligne_data else "stops"


def interpolate_last_time(arrets: list[dict]) -> list[dict]:
    """
    Après une coupe, le dernier arrêt a souvent temps=0 ou None.
    On lui attribue la moyenne des 3 derniers segments valides.
    """
    if len(arrets) < 2:
        return arrets
    arrets = copy.deepcopy(arrets)
    valeurs = [
        a.get("temps_vers_suivant_sec")
        for a in arrets[:-1]
        if a.get("temps_vers_suivant_sec") and a["temps_vers_suivant_sec"] > 0
    ]
    fallback = int(statistics.mean(valeurs[-3:])) if valeurs else 120
    last = arrets[-1]
    t = last.get("temps_vers_suivant_sec")
    if not t or t == 0:
        last["temps_vers_suivant_sec"] = fallback
    return arrets


def apply_cut(ligne_data: dict, last_idx: int) -> dict:
    """Tronque la liste d'arrêts à last_idx inclus."""
    ligne = copy.deepcopy(ligne_data)
    key = get_arrets_key(ligne)
    arrets = ligne[key]
    ligne[key] = interpolate_last_time(arrets[:last_idx + 1])
    return ligne


def apply_ranges(ligne_data: dict, ranges: list[tuple]) -> dict:
    """Concatène plusieurs plages d'arrêts (pour ligne 23)."""
    ligne = copy.deepcopy(ligne_data)
    key = get_arrets_key(ligne)
    arrets = ligne[key]
    merged = []
    for start, end in ranges:
        merged.extend(arrets[start:end + 1])
    ligne[key] = interpolate_last_time(merged)
    return ligne


def fmt_dur(s: int) -> str:
    h, r = divmod(s, 3600)
    m, sec = divmod(r, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{sec:02d}s"


def ligne_stats(arrets: list[dict]) -> str:
    valeurs = [
        a.get("temps_vers_suivant_sec", 0)
        for a in arrets[:-1]
        if a.get("temps_vers_suivant_sec")
    ]
    if not valeurs:
        return "N/A"
    return (
        f"{len(arrets)} arrêts | "
        f"durée {fmt_dur(sum(valeurs))} | "
        f"min={min(valeurs)}s max={max(valeurs)}s"
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_suspects.py routes_geometry_v13_fixed.json")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"❌ Fichier introuvable : {path}")
        sys.exit(1)

    print(f"\n📂 Chargement {path.name} ({path.stat().st_size // 1024} KB)...")
    data = load_json(str(path))
    root_key, root = get_root(data)
    data_fixed = copy.deepcopy(data)
    fixed_root = data_fixed[root_key]

    print("\n━━━  CORRECTIONS  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ── Ligne 23 ──────────────────────────────────────────
    if "23" in fixed_root:
        before = fixed_root["23"]
        ak = get_arrets_key(before)
        nb_avant = len(before[ak])
        fixed_root["23"] = apply_ranges(before, LIGNE_23_KEEP_RANGES)
        nb_apres = len(fixed_root["23"][ak])
        stats = ligne_stats(fixed_root["23"][ak])
        print(f"\n  Ligne 23  : {nb_avant} → {nb_apres} arrêts")
        print(f"    Plages conservées : {LIGNE_23_KEEP_RANGES}")
        print(f"    Résultat : {stats}")
    else:
        print("\n  Ligne 23  : introuvable dans le JSON")

    # ── Coupes simples ─────────────────────────────────────
    for lid, cut_idx in CUTS.items():
        if lid not in fixed_root:
            print(f"\n  Ligne {lid} : introuvable dans le JSON")
            continue
        before = fixed_root[lid]
        ak = get_arrets_key(before)
        nb_avant = len(before[ak])
        terminus_coupe = before[ak][cut_idx].get("nom") or before[ak][cut_idx].get("name", "?")

        fixed_root[lid] = apply_cut(before, cut_idx)
        nb_apres = len(fixed_root[lid][ak])
        stats = ligne_stats(fixed_root[lid][ak])

        flag = " ⚠️ DOUBLON de 217" if lid == "218" else ""
        print(f"\n  Ligne {lid}{flag}")
        print(f"    Coupe à [{cut_idx}] '{terminus_coupe}'")
        print(f"    {nb_avant} → {nb_apres} arrêts | {stats}")

    # ── Résumé ────────────────────────────────────────────
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("\n⚠️  Note : Ligne 218 est identique à 217 après correction.")
    print("   Envisager de supprimer 218 ou de la différencier depuis les données source.\n")

    # ── Écriture ──────────────────────────────────────────
    out_path = path.parent / (path.stem + "2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data_fixed, f, ensure_ascii=False, indent=2)

    print(f"✅ Fichier généré : {out_path}")
    print(f"   Taille : {out_path.stat().st_size // 1024} KB\n")
    print("Étape suivante : valider avec")
    print(f"  python validate_durations.py {out_path.name}\n")


if __name__ == "__main__":
    main()
