"""
services/websocket.py — V1.0
WebSocket handler pour le dashboard Xëtu.

PROTOCOLE JSON structuré :

  Client → Serveur :
    { "type": "chat",   "text": "Bus 15 ?" }
    { "type": "report", "ligne": "15", "arret": "Liberté 5", "observation": "bondé" }
    { "type": "ping" }

  Serveur → Client :
    { "type": "chat_response", "text": "Le bus 15 est à..." }
    { "type": "bus_update",    "buses": [...] }
    { "type": "report_ack",    "success": true, "id": "rpt_xxx" }
    { "type": "error",         "message": "..." }
    { "type": "pong" }
    { "type": "welcome",       "text": "Salam ! Je suis Xëtu..." }

ARCHITECTURE :
  Même Core Xëtu que WhatsApp et Telegram.
  Le session_id web_xxx est utilisé comme "phone" dans Supabase.
  Les messages WS passent par _process_message_safe() de main.py.

SÉCURITÉ :
  - session_id validé (format web_uuid4)
  - Rate limit 30 msg / session / heure (partagé avec api/report.py)
  - Messages vides ou trop longs rejetés
  - Timeout ping/pong : 60s sans message → déconnexion
"""

import json
import logging
import re
import asyncio
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

# ── Format session_id attendu ────────────────────────────
_SESSION_ID_RE = re.compile(
    r"^web_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE
)

_MAX_TEXT_LENGTH = 500
_HEARTBEAT_TIMEOUT = 60  # secondes sans message → déconnexion

# ── Message d'accueil ────────────────────────────────────
_WELCOME_TEXT = (
    "Salam ! Je suis Xëtu 🚌\n"
    "Posez-moi une question sur les bus de Dakar "
    "ou signalez une position directement ici."
)

# ── Suggestions rapides ──────────────────────────────────
_QUICK_SUGGESTIONS = [
    "Où est le bus 15 ?",
    "Bus 7 à Yoff",
    "Comment aller à Sandaga ?",
]


# ═══════════════════════════════════════════════════════════
# HANDLER PRINCIPAL
# ═══════════════════════════════════════════════════════════

async def handle_websocket(
    websocket: WebSocket,
    session_id: str,
    process_fn,       # callable → _process_message_safe de main.py
    background_tasks, # BackgroundTasks FastAPI
):
    """
    Gère une connexion WebSocket complète.

    Args:
        websocket:        connexion FastAPI WebSocket
        session_id:       identifiant de session (ex: "web_uuid4")
        process_fn:       coroutine partagée avec WA/TG pour traiter les messages
        background_tasks: BackgroundTasks FastAPI (pour notify_abonnes etc.)
    """
    # Validation du session_id
    if not _SESSION_ID_RE.match(session_id):
        await websocket.accept()
        await _send(websocket, {
            "type":    "error",
            "message": "Session ID invalide.",
        })
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info(f"[WS] Connexion ouverte — session={session_id[:20]}")

    # Prépare send_fn compatible avec le Core Xëtu
    async def send_fn(_: str, text: str) -> bool:
        return await _send(websocket, {
            "type": "chat_response",
            "text": text,
        })

    # Message d'accueil
    await _send(websocket, {
        "type":        "welcome",
        "text":        _WELCOME_TEXT,
        "suggestions": _QUICK_SUGGESTIONS,
    })

    # Boucle de réception
    try:
        while True:
            # Timeout heartbeat
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_HEARTBEAT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.info(f"[WS] Heartbeat timeout — session={session_id[:20]}")
                await websocket.close(code=4002)
                return

            # Parser le message JSON
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {
                    "type":    "error",
                    "message": "Format invalide. Envoie du JSON.",
                })
                continue

            msg_type = msg.get("type", "")

            # ── PING / PONG ───────────────────────────────
            if msg_type == "ping":
                await _send(websocket, {"type": "pong"})
                continue

            # ── CHAT ─────────────────────────────────────
            if msg_type == "chat":
                text = str(msg.get("text", "")).strip()

                if not text:
                    continue

                if len(text) > _MAX_TEXT_LENGTH:
                    await _send(websocket, {
                        "type":    "error",
                        "message": "Message trop long (500 caractères max).",
                    })
                    continue

                logger.info(
                    f"[WS] Chat — session={session_id[:20]} "
                    f"text={text[:60]!r}"
                )

                # Passe par le même Core Xëtu que WA/TG
                try:
                    await process_fn(
                        phone=session_id,
                        text=text,
                        background_tasks=background_tasks,
                        send_fn=send_fn,
                    )
                except Exception as e:
                    logger.error(f"[WS] Erreur process_fn: {e}", exc_info=True)
                    await _send(websocket, {
                        "type":    "error",
                        "message": "Erreur interne. Réessaie dans un instant.",
                    })

                continue

            # ── REPORT ───────────────────────────────────
            if msg_type == "report":
                await _handle_report(websocket, msg, session_id, background_tasks)
                continue

            # ── Type inconnu ──────────────────────────────
            logger.debug(f"[WS] Type inconnu: {msg_type!r}")
            await _send(websocket, {
                "type":    "error",
                "message": f"Type de message inconnu : {msg_type}",
            })

    except WebSocketDisconnect:
        logger.info(f"[WS] Déconnexion propre — session={session_id[:20]}")
    except Exception as e:
        logger.error(f"[WS] Erreur inattendue — session={session_id[:20]}: {e}", exc_info=True)
    finally:
        logger.info(f"[WS] Connexion fermée — session={session_id[:20]}")


# ═══════════════════════════════════════════════════════════
# HANDLER REPORT VIA WS
# ═══════════════════════════════════════════════════════════

async def _handle_report(
    websocket: WebSocket,
    msg: dict,
    session_id: str,
    background_tasks,
):
    """
    Signalement rapide depuis le chat WS.
    Même logique que POST /api/report mais via WebSocket.
    """
    from config.settings import VALID_LINES
    from db import queries

    ligne      = str(msg.get("ligne", "")).strip().upper()
    arret      = str(msg.get("arret", "")).strip()
    observation = str(msg.get("observation", "")).strip() or None

    # Validation
    if not ligne or ligne not in VALID_LINES:
        await _send(websocket, {
            "type":    "report_ack",
            "success": False,
            "error":   "Ligne inconnue.",
        })
        return

    if len(arret) < 2:
        await _send(websocket, {
            "type":    "report_ack",
            "success": False,
            "error":   "Arrêt trop court.",
        })
        return

    try:
        result = queries.save_signalement(
            ligne=ligne,
            arret=arret,
            phone=session_id,
        )

        if result is None:
            # Doublon
            await _send(websocket, {
                "type":    "report_ack",
                "success": True,
                "status":  "already_recorded",
            })
            return

        if observation:
            try:
                import skills.signalement as skill_signalement
                queries.enrichir_signalement(
                    ligne=ligne, arret=arret,
                    qualite=observation, phone=session_id
                )
            except Exception as e:
                logger.warning(f"[WS] Enrichissement échoué: {e}")

        # Notifier les abonnés
        import skills.signalement as skill_signalement
        background_tasks.add_task(
            skill_signalement.notify_abonnes, ligne, arret, session_id
        )

        report_id = f"rpt_{result.get('id', 'ok')}" if isinstance(result, dict) else "rpt_ok"

        logger.info(
            f"[WS] Report ✅ ligne={ligne} arret={arret} "
            f"obs={observation} session={session_id[:20]}"
        )

        await _send(websocket, {
            "type":    "report_ack",
            "success": True,
            "id":      report_id,
            "status":  "recorded",
        })

    except Exception as e:
        logger.error(f"[WS] Erreur report: {e}", exc_info=True)
        await _send(websocket, {
            "type":    "report_ack",
            "success": False,
            "error":   "Erreur interne.",
        })


# ═══════════════════════════════════════════════════════════
# HELPER ENVOI
# ═══════════════════════════════════════════════════════════

async def _send(websocket: WebSocket, data: dict) -> bool:
    """Envoie un message JSON. Retourne False si la connexion est fermée."""
    try:
        await websocket.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.debug(f"[WS] _send failed: {e}")
        return False
