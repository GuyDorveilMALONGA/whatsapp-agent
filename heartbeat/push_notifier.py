"""
heartbeat/push_notifier.py — V1.0
Envoie des notifications push aux abonnés PWA
quand un bus est signalé sur leur ligne.
"""
import logging
import os
import json
from pywebpush import webpush, WebPushException
from db import queries

logger = logging.getLogger(__name__)

VAPID_PRIVATE_KEY   = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIMS_EMAIL  = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:xetu@demdikk.sn")


async def run_push_notifications():
    """
    Vérifie toutes les lignes actives.
    Si un nouveau signalement existe → notifie les abonnés PWA.
    """
    if not VAPID_PRIVATE_KEY:
        logger.warning("[PushNotifier] VAPID_PRIVATE_KEY manquante — skip")
        return

    try:
        # Récupère les signalements actifs des 5 dernières minutes
        signalements = queries.get_signalements_recents(minutes=5)
        if not signalements:
            return

        logger.info(f"[PushNotifier] {len(signalements)} signalement(s) récent(s)")

        lignes_notifiees = set()

        for s in signalements:
            ligne = s.get("ligne")
            arret = s.get("position", "")

            # Une seule notif par ligne par cycle
            if ligne in lignes_notifiees:
                continue
            lignes_notifiees.add(ligne)

            # Récupère les abonnés push de cette ligne
            subscriptions = queries.get_push_subscriptions_by_ligne(ligne)
            if not subscriptions:
                continue

            logger.info(f"[PushNotifier] Ligne {ligne} → {len(subscriptions)} abonné(s)")

            payload = json.dumps({
                "title": f"🚌 Bus {ligne} signalé !",
                "body":  f"Un bus {ligne} vient d'être signalé à {arret}.",
                "tag":   f"bus-{ligne}",
                "url":   "/",
            })

            for sub in subscriptions:
                await _send_push(sub, payload)

    except Exception as e:
        logger.error(f"[PushNotifier] Erreur run_push_notifications: {e}", exc_info=True)


async def _send_push(subscription: dict, payload: str):
    """Envoie une notification push à un abonnement."""
    try:
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {
                    "p256dh": subscription["p256dh"],
                    "auth":   subscription["auth"],
                },
            },
            data=payload,
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIMS_EMAIL},
        )
    except WebPushException as e:
        # Abonnement expiré → on le supprime
        if e.response and e.response.status_code in (404, 410):
            logger.info(f"[PushNotifier] Abonnement expiré — suppression")
            try:
                queries.delete_push_subscription(
                    phone=subscription["phone"],
                    endpoint=subscription["endpoint"],
                )
            except Exception:
                pass
        else:
            logger.error(f"[PushNotifier] WebPushException: {e}")
    except Exception as e:
        logger.error(f"[PushNotifier] Erreur _send_push: {e}")