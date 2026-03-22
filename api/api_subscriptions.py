"""
api/subscriptions.py — Endpoints REST abonnements Xëtu
GET    /api/subscriptions?session_id=xxx  → liste des lignes abonnées
POST   /api/subscriptions                 → body {session_id, ligne}
DELETE /api/subscriptions/{ligne}?session_id=xxx → désactiver

Note : phone = session_id côté PWA (pas de numéro de téléphone réel)
"""
import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from db import queries

logger = logging.getLogger(__name__)
router = APIRouter()


class SubscriptionCreate(BaseModel):
    session_id: str
    ligne: str


@router.get("/api/subscriptions")
async def get_subscriptions(session_id: str = Query(...)):
    """Retourne les lignes actives pour ce session_id."""
    if not session_id or len(session_id) > 128:
        raise HTTPException(status_code=400, detail="session_id invalide")
    try:
        rows = queries.get_abonnements_actifs(session_id)
        lignes = [r["ligne"] for r in rows]
        return {"lignes": lignes}
    except Exception as e:
        logger.error(f"[Subscriptions GET] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur")


@router.post("/api/subscriptions", status_code=201)
async def create_subscription(body: SubscriptionCreate):
    """Crée ou réactive un abonnement."""
    if not body.session_id or len(body.session_id) > 128:
        raise HTTPException(status_code=400, detail="session_id invalide")
    if not body.ligne:
        raise HTTPException(status_code=400, detail="ligne manquante")
    try:
        queries.create_abonnement(body.session_id, body.ligne, "", None)
        return {"status": "ok", "ligne": body.ligne}
    except Exception as e:
        logger.error(f"[Subscriptions POST] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur")


@router.delete("/api/subscriptions/{ligne}")
async def delete_subscription(ligne: str, session_id: str = Query(...)):
    """Désactive un abonnement."""
    if not session_id or len(session_id) > 128:
        raise HTTPException(status_code=400, detail="session_id invalide")
    try:
        queries.deactivate_abonnement(session_id, ligne)
        return {"status": "ok", "ligne": ligne}
    except Exception as e:
        logger.error(f"[Subscriptions DELETE] {e}")
        raise HTTPException(status_code=500, detail="Erreur serveur")
