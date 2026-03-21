#!/usr/bin/env python3
"""
validate_terrain.py — Xëtu V8.2
Valide les aliases_terrain injectés dans routes_geometry_v13.json.

Vérifications :
  - Pas d'alias < 3 chars
  - Pas d'alias identique au nom officiel d'un arrêt de la ligne (insensible casse)
  - Pas de doublons entre aliases de la même ligne (insensible casse)
  - Pas d'alias identique entre deux lignes différentes (warning, pas erreur)

Génère un rapport : validation_terrain.txt

Usage :
  python validate_terrain.py routes_geometry_v13.json
  python validate_terrain.py routes_geometry_v13_new.json
"""

import json
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# ── Constantes ────────────────────────────────────────────────────────────────

MIN_ALIAS_LEN   = 3
REPORT_PATH     = Path("validation_terrain.txt")


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalize_key(text: str) -> str:
    """lowercase + strip accents + tirets/apostrophes → espace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_str.lower().replace("-", " ").replace("'", " ").replace("\u2019", " ").strip()


# ── Chargement ────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def iter_lines(data: dict) -> list[tuple[str, dict]]:
    root = data.get("routes") or data.get("lignes") or {}
    return sorted(root.items())


def get_arrets(line_data: dict) -> list[dict]:
    return line_data.get("arrets", line_data.get("stops", []))


def get_nom(stop: dict) -> str:
    return stop.get("nom", stop.get("name", "")).strip()


def get_official_noms(line_data: dict) -> set[str]:
    """Retourne l'ensemble des noms officiels normalisés d'une ligne."""
    return {
        normalize_key(get_nom(s))
        for s in get_arrets(line_data)
        if get_nom(s)
    }


# ── Validation par ligne ───────────────────────────────────────────────────────

class LineReport:
    def __init__(self, line_id: str):
        self.line_id   = line_id
        self.errors    = []   # bloquants
        self.warnings  = []   # non bloquants
        self.aliases   = []   # aliases validés
        self.nb_total  = 0

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)


def validate_line(line_id: str, line_data: dict) -> LineReport:
    report = LineReport(line_id)

    aliases = line_data.get("aliases_terrain", [])
    if not isinstance(aliases, list):
        report.add_error(f"aliases_terrain n'est pas une liste (type: {type(aliases).__name__})")
        return report

    if not aliases:
        return report  # pas d'aliases — skip (pas une erreur)

    report.nb_total = len(aliases)
    official_noms   = get_official_noms(line_data)
    seen_keys: dict[str, str] = {}  # normalized_key → alias original

    for alias in aliases:
        if not isinstance(alias, str):
            report.add_error(f"alias non-string : {repr(alias)}")
            continue

        alias_stripped = alias.strip()
        alias_key      = normalize_key(alias_stripped)

        # ── Règle 1 : longueur minimum ───────────────────────────────────────
        if len(alias_stripped) < MIN_ALIAS_LEN:
            report.add_error(
                f"Alias trop court ({len(alias_stripped)} char) : '{alias_stripped}'"
            )
            continue

        # ── Règle 2 : pas identique à un nom officiel ────────────────────────
        if alias_key in official_noms:
            report.add_error(
                f"Alias identique à un arrêt officiel : '{alias_stripped}' "
                f"(inutile — déjà dans les noms officiels)"
            )
            continue

        # ── Règle 3 : pas de doublons dans la ligne ──────────────────────────
        if alias_key in seen_keys:
            report.add_error(
                f"Doublon détecté : '{alias_stripped}' == '{seen_keys[alias_key]}'"
            )
            continue

        seen_keys[alias_key] = alias_stripped
        report.aliases.append(alias_stripped)

    return report


# ── Vérification inter-lignes ─────────────────────────────────────────────────

def check_cross_line_duplicates(
    all_reports: list[LineReport],
) -> list[tuple[str, str, str, str]]:
    """
    Détecte les aliases identiques entre deux lignes différentes.
    Retourne [(alias, line1, line2, alias_line2), ...] — warnings seulement.
    """
    alias_to_lines: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for rep in all_reports:
        for alias in rep.aliases:
            alias_to_lines[normalize_key(alias)].append((rep.line_id, alias))

    cross = []
    for alias_key, occurrences in alias_to_lines.items():
        if len(occurrences) > 1:
            line1, a1 = occurrences[0]
            for line2, a2 in occurrences[1:]:
                cross.append((a1, line1, a2, line2))
    return cross


# ── Rapport ───────────────────────────────────────────────────────────────────

def build_report(
    json_path: Path,
    lines: list[tuple[str, dict]],
    all_reports: list[LineReport],
    cross_dups: list[tuple],
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines_with_terrain = [r for r in all_reports if r.nb_total > 0]
    lines_with_errors  = [r for r in all_reports if not r.ok]
    total_aliases      = sum(r.nb_total for r in all_reports)
    valid_aliases      = sum(len(r.aliases) for r in all_reports)

    out = []
    out.append("=" * 72)
    out.append("  RAPPORT VALIDATION ALIASES TERRAIN — Xëtu V8.2")
    out.append(f"  Généré le : {now}")
    out.append(f"  Source    : {json_path.resolve()}")
    out.append("=" * 72)
    out.append("")

    # ── Stats globales ────────────────────────────────────────────────────────
    out.append("━━━  STATS GLOBALES  " + "━" * 51)
    out.append(f"  Lignes dans le JSON      : {len(lines)}")
    out.append(f"  Lignes avec aliases      : {len(lines_with_terrain)}")
    out.append(f"  Total aliases bruts      : {total_aliases}")
    out.append(f"  Aliases valides          : {valid_aliases}")
    out.append(f"  Aliases en erreur        : {total_aliases - valid_aliases}")
    out.append(f"  Lignes avec erreurs      : {len(lines_with_errors)}")
    out.append(f"  Duplicats inter-lignes   : {len(cross_dups)} (warnings)")
    out.append("")

    # ── Détail par ligne (erreurs uniquement) ─────────────────────────────────
    if lines_with_errors:
        out.append("━━━  ERREURS PAR LIGNE  " + "━" * 48)
        for rep in lines_with_errors:
            out.append(f"")
            out.append(f"  ❌  Ligne {rep.line_id}")
            for err in rep.errors:
                out.append(f"      • {err}")
        out.append("")

    # ── Warnings inter-lignes ─────────────────────────────────────────────────
    if cross_dups:
        out.append("━━━  DUPLICATS INTER-LIGNES (warnings)  " + "━" * 31)
        for a1, l1, a2, l2 in cross_dups:
            out.append(f"  ⚠️   '{a1}' (ligne {l1})  ==  '{a2}' (ligne {l2})")
        out.append("")

    # ── Résumé par ligne (toutes celles avec aliases) ─────────────────────────
    out.append("━━━  DÉTAIL PAR LIGNE (avec aliases)  " + "━" * 34)
    for rep in all_reports:
        if rep.nb_total == 0:
            continue
        status = "✅" if rep.ok else "❌"
        out.append(
            f"  {status}  {rep.line_id:12s}  "
            f"{len(rep.aliases):3d} valides / {rep.nb_total:3d} total"
        )
        if rep.aliases:
            preview = ", ".join(rep.aliases[:5])
            if len(rep.aliases) > 5:
                preview += f" … (+{len(rep.aliases) - 5})"
            out.append(f"           → {preview}")

    out.append("")
    out.append("━" * 72)
    verdict = "✅ VALIDATION OK" if not lines_with_errors else f"❌ {len(lines_with_errors)} LIGNE(S) EN ERREUR"
    out.append(f"  {verdict}")
    out.append("━" * 72)
    out.append("")

    return "\n".join(out)


# ── Console summary ───────────────────────────────────────────────────────────

def print_console_summary(all_reports: list[LineReport], cross_dups: list):
    lines_with_terrain = [r for r in all_reports if r.nb_total > 0]
    lines_with_errors  = [r for r in all_reports if not r.ok]
    total_aliases      = sum(r.nb_total for r in all_reports)
    valid_aliases      = sum(len(r.aliases) for r in all_reports)

    print()
    print("━━━  RÉSUMÉ VALIDATION  " + "━" * 48)
    print(f"  Lignes avec aliases      : {len(lines_with_terrain)}")
    print(f"  Total aliases            : {total_aliases}")
    print(f"  Valides                  : {valid_aliases}")
    print(f"  Erreurs                  : {total_aliases - valid_aliases}")
    if cross_dups:
        print(f"  Duplicats inter-lignes   : {len(cross_dups)} (warnings)")
    print()

    if lines_with_errors:
        print(f"  ❌ {len(lines_with_errors)} ligne(s) avec erreurs :")
        for rep in lines_with_errors:
            print(f"     • Ligne {rep.line_id} : {len(rep.errors)} erreur(s)")
            for err in rep.errors[:3]:
                print(f"       - {err}")
            if len(rep.errors) > 3:
                print(f"       … (+{len(rep.errors) - 3} autres, voir rapport)")
        print()
    else:
        print("  ✅ Aucune erreur détectée")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage : python validate_terrain.py routes_geometry_v13.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])
    if not json_path.exists():
        print(f"❌ Fichier introuvable : {json_path}", file=sys.stderr)
        sys.exit(1)

    print(f"\n📂 Chargement : {json_path} ({json_path.stat().st_size // 1024} KB)...")
    data  = load_json(json_path)
    lines = iter_lines(data)
    print(f"   {len(lines)} lignes trouvées\n")

    # ── Validation par ligne ──────────────────────────────────────────────────
    all_reports: list[LineReport] = []
    for line_id, line_data in lines:
        rep = validate_line(line_id, line_data)
        all_reports.append(rep)

    # ── Cross-line duplicates ─────────────────────────────────────────────────
    cross_dups = check_cross_line_duplicates(all_reports)

    # ── Console ───────────────────────────────────────────────────────────────
    print_console_summary(all_reports, cross_dups)

    # ── Rapport fichier ───────────────────────────────────────────────────────
    report_text = build_report(json_path, lines, all_reports, cross_dups)
    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"  📋 Rapport complet : {REPORT_PATH.resolve()}")
    print()

    # Exit code non-zéro si erreurs (utile pour CI)
    has_errors = any(not r.ok for r in all_reports)
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
