"""
api/leaderboard.py
GET /api/leaderboard — Top signaleurs gamifiés.

Utilise fiabilite_score et le nombre de signalements
depuis la table contacts + signalements.
"""

import logging
from fastapi import APIRouter
from db import queries

logger = logging.getLogger(__name__)
router = APIRouter()


def _badge(nb_signalements: int) -> dict:
    """Retourne le badge selon le nombre de signalements."""
    if nb_signalements >= 100:
        return {"emoji": "🏆", "label": "Légende",  "niveau": 4}
    elif nb_signalements >= 51:
        return {"emoji": "🥇", "label": "Expert",   "niveau": 3}
    elif nb_signalements >= 11:
        return {"emoji": "🥈", "label": "Régulier", "niveau": 2}
    else:
        return {"emoji": "🥉", "label": "Nouveau",  "niveau": 1}


def _masquer_phone(phone: str) -> str:
    """Masque le numéro : +221 77 **** 1234"""
    if len(phone) >= 4:
        return f"**** {phone[-4:]}"
    return "****"


@router.get("/api/leaderboard")
async def get_leaderboard():
    """
    Retourne le top 10 des signaleurs + stats globales communauté.
    """
    try:
        data = queries.get_leaderboard()
    except Exception as e:
        logger.error(f"[/api/leaderboard] Erreur: {e}")
        return {"leaderboard": [], "stats": {}, "error": "db_error"}

    leaderboard = []
    for i, entry in enumerate(data[:10]):
        nb   = entry.get("nb_signalements", 0)
        score = entry.get("fiabilite_score", 0.5)
        badge = _badge(nb)
        leaderboard.append({
            "rang":            i + 1,
            "pseudo":          _masquer_phone(entry.get("phone", "")),
            "nb_signalements": nb,
            "fiabilite_score": round(score * 100),  # 0–100
            "badge":           badge,
        })

    # Stats globales
    try:
        stats = queries.get_stats_communaute()
    except Exception:
        stats = {}

    return {
        "leaderboard": leaderboard,
        "stats": {
            "total_signalements_aujourd_hui": stats.get("aujourd_hui", 0),
            "total_signalements_all_time":    stats.get("all_time", 0),
            "nb_contributeurs":               stats.get("nb_contributeurs", 0),
        }
    }
