#!/usr/bin/env python3
"""
generate_terrain_input.py — Xëtu V8.2
Génère les fichiers .txt à remplir manuellement pour les aliases terrain.

Règles :
  - Exclut les lignes AVEC aliases_terrain déjà renseignés
  - Exclut L1, L4 (noms GTFS déjà terrain par nature)
  - Exclut lignes ddd_xxx (interurbaines) et L501-503
  - Génère EN PREMIER les 5 lignes prioritaires : L2, L12, L16B, TO1, TAF TAF
  - Crée terrain_input/ si absent

Usage :
  python generate_terrain_input.py routes_geometry_v13.json
"""

import json
import sys
import os
from pathlib import Path

# ── Constantes ────────────────────────────────────────────────────────────────

EXCLUDED_ALWAYS = {"L1", "L4", "1", "4"}          # GTFS — terrain par nature
EXCLUDED_SCOPE  = {"501", "502", "503",            # hors scope
                   "L501", "L502", "L503"}

PRIORITY_LINES = ["2", "12", "16B", "TO1", "TAF TAF"]   # ordre démo Dem Dikk

OUTPUT_DIR = Path("terrain_input")


# ── Helpers ───────────────────────────────────────────────────────────────────

def normalize_id(line_id: str) -> str:
    """Retourne l'ID normalisé (ex: '2', '16B', 'TAF TAF') sans préfixe L."""
    return str(line_id).strip().upper()


def is_excluded(line_id: str) -> bool:
    nid = normalize_id(line_id)
    if nid in EXCLUDED_ALWAYS:
        return True
    if nid in EXCLUDED_SCOPE:
        return True
    # ddd_xxx — lignes interurbaines
    if nid.startswith("DDD_") or line_id.lower().startswith("ddd_"):
        return True
    return False


def has_terrain(line_data: dict) -> bool:
    aliases = line_data.get("aliases_terrain", [])
    return isinstance(aliases, list) and len(aliases) > 0


def get_arrets(line_data: dict) -> list[dict]:
    return line_data.get("arrets", line_data.get("stops", []))


def get_nom(stop: dict) -> str:
    return stop.get("nom", stop.get("name", "")).strip()


def get_line_meta(line_id: str, line_data: dict) -> tuple[str, str, str]:
    """Retourne (nom_ligne, terminus_a, terminus_b)."""
    nom = line_data.get("nom", line_data.get("name", f"Ligne {line_id}"))
    ta  = line_data.get("terminus_a", "?")
    tb  = line_data.get("terminus_b", "?")
    return nom, ta, tb


def write_input_file(line_id: str, line_data: dict, output_dir: Path) -> Path:
    """Génère le fichier terrain_input/L{id}.txt et retourne le chemin."""
    nom, ta, tb = get_line_meta(line_id, line_data)
    arrets = get_arrets(line_data)

    # Nom de fichier safe (TAF TAF → LTAF_TAF.txt)
    safe_id = line_id.replace(" ", "_")
    filepath = output_dir / f"L{safe_id}.txt"

    lines = [
        f"# Ligne {line_id} — {nom} ({ta} → {tb})",
        f"# Remplis la colonne NOM_TERRAIN (laisse vide si identique au nom officiel)",
        f"# Une ligne par arrêt. Format : NOM_OFFICIEL | NOM_TERRAIN",
        f"# Exemple : Terminus Ouakam | Gare Ouakam",
        f"# Lignes commençant par # sont ignorées à l'import.",
        f"#",
        f"# {len(arrets)} arrêts sur cette ligne.",
        f"",
    ]

    for stop in arrets:
        nom_off = get_nom(stop)
        if nom_off:
            lines.append(f"{nom_off} |")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage : python generate_terrain_input.py routes_geometry_v13.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ Fichier introuvable : {json_path}", file=sys.stderr)
        sys.exit(1)

    print(f"📂 Chargement : {json_path} ({json_path.stat().st_size // 1024} KB)...")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    root = data.get("routes") or data.get("lignes") or {}
    if not root:
        print("❌ JSON invalide : ni 'routes' ni 'lignes' trouvé.", file=sys.stderr)
        sys.exit(1)

    print(f"   {len(root)} lignes dans le JSON\n")

    # Création dossier output
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── Partitionner : prioritaires vs reste ─────────────────────────────────
    priority_ids   = []   # lignes prioritaires dans l'ordre demandé
    remaining_ids  = []   # autres lignes sans terrain, non exclues
    already_done   = []   # avec aliases_terrain déjà présents
    excluded_list  = []   # exclues (GTFS, ddd, hors scope)

    for line_id, line_data in root.items():
        nid = normalize_id(line_id)

        if is_excluded(line_id):
            excluded_list.append(line_id)
            continue

        if has_terrain(line_data):
            already_done.append(line_id)
            continue

        if nid in [normalize_id(p) for p in PRIORITY_LINES]:
            priority_ids.append(line_id)
        else:
            remaining_ids.append(line_id)

    # Réordonner priority_ids selon l'ordre PRIORITY_LINES
    priority_norm_to_id = {normalize_id(lid): lid for lid in priority_ids}
    ordered_priority = []
    for p in PRIORITY_LINES:
        pn = normalize_id(p)
        if pn in priority_norm_to_id:
            ordered_priority.append(priority_norm_to_id[pn])

    # Trier le reste alphabétiquement
    remaining_ids.sort()

    all_to_generate = ordered_priority + remaining_ids

    # ── Génération ───────────────────────────────────────────────────────────
    generated = []
    for line_id in all_to_generate:
        line_data = root[line_id]
        fp = write_input_file(normalize_id(line_id), line_data, OUTPUT_DIR)
        generated.append((line_id, fp, len(get_arrets(line_data))))
        print(f"  ✅ {normalize_id(line_id):>10}  →  {fp}  ({len(get_arrets(line_data))} arrêts)")

    # ── Résumé ───────────────────────────────────────────────────────────────
    print()
    print("━━━  RÉSUMÉ  " + "━" * 60)
    print(f"  Fichiers générés      : {len(generated)}")
    print(f"    └─ Prioritaires     : {len(ordered_priority)}  {[normalize_id(x) for x in ordered_priority]}")
    print(f"    └─ Autres           : {len(remaining_ids)}")
    print(f"  Déjà avec terrain     : {len(already_done)}")
    print(f"  Exclus (GTFS/hors scope/ddd) : {len(excluded_list)}")
    print(f"  Dossier output        : {OUTPUT_DIR.resolve()}")
    print()
    print("→ Remplis les fichiers NOM_OFFICIEL | NOM_TERRAIN")
    print("→ Lance ensuite : python import_terrain.py")


if __name__ == "__main__":
    main()
