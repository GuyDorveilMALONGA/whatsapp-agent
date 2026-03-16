"""
services/websocket.py — V1.6
Fix : _HEARTBEAT_TIMEOUT 60 → 120s + first_visit dans welcome + typing indicators
"""

import json
import logging
import re
import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTasks

logger = logging.getLogger(__name__)

# FIX BUG-M3 : regex assouplie — accepte tout ID alphanumérique 8-64 chars
# (l'ancienne imposait strictement UUID v4 → rejetait les variantes légitimes)
_SESSION_ID_RE = re.compile(
    r"^web_[0-9a-zA-Z_-]{8,64}$",
    re.IGNORECASE
)

_MAX_TEXT_LENGTH    = 500
_HEARTBEAT_TIMEOUT  = 120  # ← FIX V1.5 : 60 → 120s (marge suffisante pour LLM)

_WELCOME_TEXT = (
    "Salam ! Je suis Xëtu 🚌\n"
    "Posez-moi une question sur les bus de Dakar "
    "ou signalez une position directement ici."
)

_QUICK_SUGGESTIONS = [
    "Où est le bus 15 ?",
    "Bus 7 à Yoff",
    "Comment aller à Sandaga ?",
]


class AsyncBackgroundTasks(BackgroundTasks):
    def add_task(self, func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            asyncio.create_task(func(*args, **kwargs))
        else:
            super().add_task(func, *args, **kwargs)


async def handle_websocket(websocket, session_id, process_fn, background_tasks=None):
    background_tasks = AsyncBackgroundTasks()

    if not _SESSION_ID_RE.match(session_id):
        await websocket.accept()
        await _send(websocket, {"type": "error", "message": "Session ID invalide."})
        await websocket.close(code=4001)
        return

    await websocket.accept()
    logger.info(f"[WS] Connexion ouverte — session={session_id[:20]}")

    async def send_fn(_phone, text):
        return await _send(websocket, {"type": "chat_response", "text": text})

    # FIX V1.5 : first_visit=True pour afficher le message de bienvenue
    await _send(websocket, {
        "type": "welcome",
        "text": _WELCOME_TEXT,
        "suggestions": _QUICK_SUGGESTIONS,
        "first_visit": True,
    })

    try:
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=_HEARTBEAT_TIMEOUT)
            except asyncio.TimeoutError:
                logger.info(f"[WS] Heartbeat timeout — session={session_id[:20]}")
                await websocket.close(code=4002)
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {"type": "error", "message": "Format invalide."})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await _send(websocket, {"type": "pong"})
                continue

            if msg_type == "chat":
                text = str(msg.get("text", "")).strip()
                if not text:
                    continue
                if len(text) > _MAX_TEXT_LENGTH:
                    await _send(websocket, {"type": "error", "message": "Message trop long (500 caractères max)."})
                    continue

                logger.info(f"[WS] Chat — session={session_id[:20]} text={text[:60]!r}")

                # FIX V1.5 : envoyer typing=true avant le traitement
                await _send(websocket, {"type": "typing", "active": True})

                try:
                    # FIX BUG-C6 : sérialiser via queue_manager (comme WhatsApp/Telegram)
                    import core.queue_manager as queue_manager
                    async with queue_manager.process(session_id):
                        await process_fn(phone=session_id, text=text, background_tasks=background_tasks, send_fn=send_fn)
                except TimeoutError:
                    logger.warning(f"[WS] Queue timeout pour session={session_id[:20]}")
                    await _send(websocket, {"type": "typing", "active": False})
                    await _send(websocket, {"type": "error", "message": "Trop de messages simultanés. Réessaie."})
                    continue
                except Exception as e:
                    logger.error(f"[WS] Erreur process_fn: {e}", exc_info=True)
                    await _send(websocket, {"type": "typing", "active": False})
                    await _send(websocket, {"type": "error", "message": "Erreur interne. Réessaie dans un instant."})
                    continue

                # FIX V1.5 : envoyer typing=false après le traitement
                await _send(websocket, {"type": "typing", "active": False})
                continue

            if msg_type == "report":
                await _handle_report(websocket, msg, session_id, background_tasks)
                continue

            logger.debug(f"[WS] Type inconnu: {msg_type!r}")
            await _send(websocket, {"type": "error", "message": f"Type inconnu : {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"[WS] Déconnexion propre — session={session_id[:20]}")
    except Exception as e:
        logger.error(f"[WS] Erreur inattendue — session={session_id[:20]}: {e}", exc_info=True)
    finally:
        logger.info(f"[WS] Connexion fermée — session={session_id[:20]}")


async def _handle_report(websocket, msg, session_id, background_tasks):
    from config.settings import VALID_LINES
    from db import queries

    ligne       = str(msg.get("ligne", "")).strip().upper()
    arret       = str(msg.get("arret", "")).strip()
    observation = str(msg.get("observation", "")).strip() or None

    if not ligne or ligne not in VALID_LINES:
        await _send(websocket, {"type": "report_ack", "success": False, "error": "Ligne inconnue."})
        return
    if len(arret) < 2:
        await _send(websocket, {"type": "report_ack", "success": False, "error": "Arrêt trop court."})
        return

    try:
        result = queries.save_signalement(ligne=ligne, arret=arret, phone=session_id)
        if result is None:
            await _send(websocket, {"type": "report_ack", "success": True, "status": "already_recorded"})
            return

        if observation:
            try:
                queries.enrichir_signalement(ligne=ligne, arret=arret, qualite=observation, phone=session_id)
            except Exception as e:
                logger.warning(f"[WS] Enrichissement échoué: {e}")

        import skills.signalement as skill_signalement
        background_tasks.add_task(skill_signalement.notify_abonnes, ligne, arret, session_id)

        report_id = f"rpt_{result.get('id', 'ok')}" if isinstance(result, dict) else "rpt_ok"
        logger.info(f"[WS] Report ✅ ligne={ligne} arret={arret} obs={observation} session={session_id[:20]}")
        await _send(websocket, {"type": "report_ack", "success": True, "id": report_id, "status": "recorded"})

    except Exception as e:
        logger.error(f"[WS] Erreur report: {e}", exc_info=True)
        await _send(websocket, {"type": "report_ack", "success": False, "error": "Erreur interne."})


async def _send(websocket, data):
    try:
        await websocket.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.debug(f"[WS] _send failed: {e}")
        return False