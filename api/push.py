"""
api/push.py — V2.0
Endpoints Web Push VAPID pour Xëtu PWA.

V2.0 :
  - Payload push contient : title, body, ligne, url
  - send_push_notification() exportée pour skills/signalement.py
  - Logs détaillés pour debug démo
  - VAPID_PRIVATE_KEY + VAPID_PUBLIC_KEY depuis os.environ
"""
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db import queries

logger = logging.getLogger(__name__)
router = APIRouter()

# ── VAPID config ──────────────────────────────────────────
# Générer les clés : python -c "from pywebpush import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key, v.private_key)"
# Puis mettre dans Railway env vars : VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_CLAIMS_EMAIL

VAPID_PRIVATE_KEY  = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY   = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:hello@xetu.sn")


# ── Modèles ───────────────────────────────────────────────

class PushSubscription(BaseModel):
    phone:    str
    endpoint: str
    keys:     dict  # {p256dh, auth}


# ── Endpoints ─────────────────────────────────────────────

@router.get("/api/push/vapid-public-key")
async def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        logger.error("[Push] VAPID_PUBLIC_KEY manquante dans les env vars")
        raise HTTPException(status_code=500, detail="VAPID non configuré")
    return {"publicKey": VAPID_PUBLIC_KEY}


@router.post("/api/push/subscribe", status_code=201)
async def subscribe(body: PushSubscription):
    if not body.phone or not body.endpoint:
        raise HTTPException(status_code=400, detail="phone et endpoint requis")
    try:
        p256dh = body.keys.get("p256dh", "")
        auth   = body.keys.get("auth", "")
        queries.save_push_subscription(body.phone, body.endpoint, p256dh, auth)
        logger.info(f"[Push] ✅ Abonnement enregistré — phone=…{body.phone[-6:]} endpoint=…{body.endpoint[-20:]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Push] Erreur save_push_subscription: {e}")
        raise HTTPException(status_code=500, detail="Erreur enregistrement")


@router.delete("/api/push/unsubscribe")
async def unsubscribe(
    phone:    str = Query(...),
    endpoint: str = Query(...),
):
    try:
        queries.delete_push_subscription(phone, endpoint)
        logger.info(f"[Push] ✅ Désabonnement — phone=…{phone[-6:]}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[Push] Erreur delete_push_subscription: {e}")
        raise HTTPException(status_code=500, detail="Erreur désabonnement")


# ── Envoi push (appelé par skills/signalement.py) ─────────

async def send_push_notification(
    phone:  str,
    ligne:  str,
    arret:  str,
    titre:  Optional[str] = None,
    corps:  Optional[str] = None,
) -> bool:
    """
    Envoie une notification push à tous les abonnements actifs du phone.
    Payload : { title, body, ligne, url }
    Retourne True si au moins un envoi réussi.
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.warning("[Push] VAPID non configuré — envoi ignoré")
        return False

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("[Push] pywebpush non installé — pip install pywebpush")
        return False

    title = titre or f"🚌 Bus {ligne} signalé"
    body  = corps or f"Bus {ligne} à {arret} — signalement communautaire"

    payload = json.dumps({
        "title": title,
        "body":  body,
        "ligne": ligne,
        "url":   "/",
    })

    try:
        subscriptions = queries.get_push_subscriptions_by_phone(phone)
    except Exception as e:
        logger.error(f"[Push] Erreur get_push_subscriptions: {e}")
        return False

    if not subscriptions:
        logger.info(f"[Push] Aucun abonnement push pour {phone[-6:]}")
        return False

    success_count = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {
                        "p256dh": sub["p256dh"],
                        "auth":   sub["auth"],
                    },
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
            )
            success_count += 1
            logger.info(f"[Push] ✅ Envoyé à …{sub['endpoint'][-20:]}")
        except WebPushException as e:
            status = e.response.status_code if e.response else "?"
            logger.warning(f"[Push] ❌ Échec envoi (HTTP {status}): {e}")
            # Subscription expirée — nettoyer
            if e.response and e.response.status_code in (404, 410):
                try:
                    queries.delete_push_subscription(phone, sub["endpoint"])
                    logger.info(f"[Push] Subscription expirée supprimée")
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[Push] Erreur inattendue: {e}")

    logger.info(f"[Push] {success_count}/{len(subscriptions)} notifications envoyées pour Bus {ligne}")
    return success_count > 0
