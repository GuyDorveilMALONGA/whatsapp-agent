import json

data = json.load(open('routes_geometry_v13_fixed.json', encoding='utf-8'))
root = data.get('routes') or data.get('lignes')

SUSPECTS = ['23', '121', '217', '218', '220']

for lid in SUSPECTS:
    ligne = root.get(lid)
    if not ligne:
        print(f"Ligne {lid} introuvable\n")
        continue
    arrets = ligne.get('arrets') or ligne.get('stops') or []
    print(f"\n{'='*60}")
    print(f"Ligne {lid} — {ligne.get('nom', '')} — {len(arrets)} arrêts")
    print(f"{'='*60}")
    for i, a in enumerate(arrets):
        nom = a.get('nom') or a.get('name') or ''
        t   = a.get('temps_vers_suivant_sec', '—')
        print(f"  [{i:3d}] {nom:<45} {t}s")
