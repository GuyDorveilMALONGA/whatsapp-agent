"""
api/push.py — V1.0
Endpoints Push Notifications PWA
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from db import queries

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/push", tags=["push"])


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    phone: str
    endpoint: str
    keys: PushSubscriptionKeys


@router.post("/subscribe")
async def subscribe(data: PushSubscriptionRequest):
    try:
        queries.save_push_subscription(
            phone=data.phone,
            endpoint=data.endpoint,
            p256dh=data.keys.p256dh,
            auth=data.keys.auth,
        )
        logger.info(f"[Push] Abonnement enregistré — {data.phone[:24]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Push] Erreur subscribe: {e}")
        raise HTTPException(status_code=500, detail="Erreur enregistrement")


@router.delete("/unsubscribe")
async def unsubscribe(phone: str, endpoint: str):
    try:
        queries.delete_push_subscription(phone=phone, endpoint=endpoint)
        logger.info(f"[Push] Désabonnement — {phone[:24]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Push] Erreur unsubscribe: {e}")
        raise HTTPException(status_code=500, detail="Erreur désabonnement")


@router.get("/vapid-public-key")
async def get_vapid_public_key():
    import os
    key = os.getenv("VAPID_PUBLIC_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="VAPID_PUBLIC_KEY manquante")
    return {"publicKey": key}