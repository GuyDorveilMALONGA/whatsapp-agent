#!/usr/bin/env python3
"""
import_terrain.py — Xëtu V8.2
Lit les fichiers terrain_input/L*.txt et injecte les aliases_terrain
dans routes_geometry_v13.json.

Règles d'import :
  - Ignore lignes vides et commentaires (#)
  - Ignore entrées sans NOM_TERRAIN après le | (laissées vides)
  - Strip + déduplication sur les aliases par ligne
  - Pas d'écrasement des aliases existants : fusion (union)
  - Sauvegarde par défaut sur routes_geometry_v13_new.json
    (passer --overwrite pour écraser le fichier original)

Usage :
  python import_terrain.py
  python import_terrain.py --overwrite
  python import_terrain.py --input terrain_input/ --json routes_geometry_v13.json
"""

import json
import sys
import argparse
import shutil
from pathlib import Path
from collections import defaultdict


# ── Constantes ────────────────────────────────────────────────────────────────

DEFAULT_JSON    = "routes_geometry_v13.json"
DEFAULT_INPUT   = Path("terrain_input")
DEFAULT_OUTPUT  = "routes_geometry_v13_new.json"


# ── Parsing des fichiers .txt ──────────────────────────────────────────────────

def parse_txt_file(filepath: Path) -> tuple[str, list[str]]:
    """
    Parse un fichier terrain_input/L{id}.txt.
    Retourne (line_id, [alias1, alias2, ...]).
    line_id est extrait du nom de fichier (ex: LTAF_TAF.txt → TAF TAF).
    """
    # Nom de fichier → ID ligne
    stem = filepath.stem  # ex: L16B, LTAF_TAF, LTO1
    if not stem.startswith("L"):
        return "", []

    raw_id = stem[1:]                          # retire le L initial
    line_id = raw_id.replace("_", " ").upper() # LTAF_TAF → TAF TAF

    aliases = []
    for raw_line in filepath.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        # Ignorer vides et commentaires
        if not line or line.startswith("#"):
            continue

        # Format attendu : NOM_OFFICIEL | NOM_TERRAIN
        if "|" not in line:
            continue

        parts = line.split("|", maxsplit=1)
        if len(parts) != 2:
            continue

        nom_terrain = parts[1].strip()

        # Ignorer les vides (rempli mais pas de terrain)
        if not nom_terrain:
            continue

        aliases.append(nom_terrain)

    return line_id, aliases


def load_all_inputs(input_dir: Path) -> dict[str, list[str]]:
    """
    Charge tous les L*.txt du dossier input.
    Retourne {line_id: [aliases dédupliqués]}.
    """
    if not input_dir.exists():
        print(f"❌ Dossier introuvable : {input_dir}", file=sys.stderr)
        sys.exit(1)

    txt_files = sorted(input_dir.glob("L*.txt"))
    if not txt_files:
        print(f"⚠️  Aucun fichier L*.txt trouvé dans {input_dir}", file=sys.stderr)
        return {}

    result: dict[str, list[str]] = {}
    for fp in txt_files:
        line_id, aliases = parse_txt_file(fp)
        if not line_id:
            print(f"  ⚠️  Ignoré (nom invalide) : {fp.name}")
            continue
        if not aliases:
            continue  # aucun alias renseigné → skip silencieux

        # Déduplication en conservant l'ordre
        seen: set[str] = set()
        deduped = []
        for a in aliases:
            key = a.lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(a.strip())

        result[line_id] = deduped
        print(f"  📄 {fp.name:20s}  →  ligne {line_id:10s}  |  {len(deduped)} alias(es)")

    return result


# ── Injection dans le JSON ─────────────────────────────────────────────────────

def find_line_key(root: dict, target_id: str) -> str | None:
    """
    Cherche la clé JSON correspondant à target_id.
    Gère casse et espaces (ex: "TAF TAF", "taf taf", "16B", "16b").
    Retourne la clé telle qu'elle existe dans root, ou None.
    """
    target_norm = target_id.strip().upper()
    for key in root:
        if str(key).strip().upper() == target_norm:
            return key
    return None


def inject_aliases(root: dict, terrain_map: dict[str, list[str]]) -> dict:
    """
    Injecte les aliases dans chaque ligne concernée.
    Fusionne avec les aliases existants (pas d'écrasement).
    Retourne un dict de stats : {line_id: {added, merged, key_found}}.
    """
    stats = {}

    for target_id, new_aliases in terrain_map.items():
        key = find_line_key(root, target_id)

        if key is None:
            stats[target_id] = {"status": "NOT_FOUND", "added": 0}
            continue

        existing = root[key].get("aliases_terrain", [])
        if not isinstance(existing, list):
            existing = []

        # Union — pas de doublons (insensible à la casse)
        existing_lower = {a.lower() for a in existing}
        to_add = [a for a in new_aliases if a.lower() not in existing_lower]

        root[key]["aliases_terrain"] = existing + to_add

        stats[target_id] = {
            "status":   "OK",
            "key":      key,
            "existing": len(existing),
            "added":    len(to_add),
            "total":    len(existing) + len(to_add),
        }

    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Import aliases terrain dans routes_geometry_v13.json"
    )
    parser.add_argument(
        "--json",
        default=DEFAULT_JSON,
        help=f"Chemin vers le JSON réseau (défaut : {DEFAULT_JSON})",
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help=f"Dossier terrain_input (défaut : {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=f"Écrase le JSON original (sinon sauvegarde dans {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    json_path   = Path(args.json)
    input_dir   = Path(args.input)
    output_path = json_path if args.overwrite else Path(DEFAULT_OUTPUT)

    # ── Chargement JSON ──────────────────────────────────────────────────────
    if not json_path.exists():
        print(f"❌ JSON introuvable : {json_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n📂 Chargement JSON : {json_path} ({json_path.stat().st_size // 1024} KB)...")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    root_key = "routes" if "routes" in data else "lignes"
    root = data[root_key]
    print(f"   {len(root)} lignes trouvées (racine: '{root_key}')\n")

    # ── Lecture des fichiers terrain ─────────────────────────────────────────
    print(f"📁 Lecture des fichiers terrain : {input_dir}/")
    terrain_map = load_all_inputs(input_dir)
    print()

    if not terrain_map:
        print("ℹ️  Aucun alias à importer. Vérifiez que les fichiers sont remplis.")
        sys.exit(0)

    print(f"   {len(terrain_map)} ligne(s) avec aliases à injecter\n")

    # ── Injection ────────────────────────────────────────────────────────────
    stats = inject_aliases(root, terrain_map)

    # ── Sauvegarde ───────────────────────────────────────────────────────────
    if args.overwrite and json_path == output_path:
        # Backup de sécurité avant écrasement
        backup = json_path.with_suffix(".json.bak")
        shutil.copy2(json_path, backup)
        print(f"  💾 Backup créé : {backup}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  ✅ Sauvegardé : {output_path}\n")

    # ── Résumé ───────────────────────────────────────────────────────────────
    total_added   = 0
    total_lines   = 0
    not_found     = []

    print("━━━  RÉSUMÉ INJECTION  " + "━" * 49)
    for line_id, s in sorted(stats.items()):
        if s["status"] == "NOT_FOUND":
            not_found.append(line_id)
            print(f"  ⚠️  {line_id:12s}  clé introuvable dans le JSON")
        else:
            total_added += s["added"]
            if s["added"] > 0:
                total_lines += 1
            merged_info = f"(+{s['added']} ajoutés, {s['existing']} existants → {s['total']} total)"
            print(f"  ✅  {line_id:12s}  {merged_info}")

    print()
    print(f"  Total aliases ajoutés : {total_added}")
    print(f"  Lignes mises à jour   : {total_lines}")
    if not_found:
        print(f"  ❌ Lignes non trouvées : {not_found}")
    print(f"  Fichier de sortie     : {output_path.resolve()}")
    print()
    print("→ Lance ensuite : python validate_terrain.py " + str(output_path))


if __name__ == "__main__":
    main()
