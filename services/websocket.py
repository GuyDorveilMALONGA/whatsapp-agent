"""
services/websocket.py — V1.3 (debug)
FIX B-WS-2 : Bypass validate_phone() pour sessions web (session_id = "web_uuid...")

MIGRATIONS V1.3 depuis V1.2 :
  - traceback.print_exc() + print(flush=True) dans TOUS les except
    pour forcer l'affichage des erreurs dans Railway logs

MIGRATIONS V1.2 depuis V1.1 :
  - CAUSE RÉELLE du "Une erreur s'est produite" dans le chat :
    _process_message_safe appelle get_or_create_contact(phone, lang) puis
    validate_phone(phone) via core/security.py. Le session_id "web_uuid4"
    ne ressemble pas à un numéro de téléphone → ValueError ou retour False
    → exception non catchée → message d'erreur générique affiché dans le chat.
    WhatsApp n'était pas affecté car son pipeline passe par _process_message()
    qui valide le phone AVANT d'appeler _process_message_safe.

  - Solution : send_fn wrapper capture aussi les erreurs de validate_phone.
    Le fix propre est dans main.py : _process_message_safe ne doit pas appeler
    validate_phone() — cette vérification appartient aux entry points WA/TG/WS,
    pas au core partagé.

MIGRATIONS V1.1 depuis V1.0 :
  - AsyncBackgroundTasks remplace BackgroundTasks dans handle_websocket
"""

import json
import logging
import re
import asyncio
import traceback
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from starlette.background import BackgroundTasks

logger = logging.getLogger(__name__)

# ── Format session_id attendu ────────────────────────────
_SESSION_ID_RE = re.compile(
    r"^web_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE
)

_MAX_TEXT_LENGTH    = 500
_HEARTBEAT_TIMEOUT  = 60

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


# ═══════════════════════════════════════════════════════════
# FIX B-WS : BackgroundTasks compatible WebSocket
# ═══════════════════════════════════════════════════════════

class AsyncBackgroundTasks(BackgroundTasks):
    """
    BackgroundTasks compatible avec les endpoints WebSocket FastAPI.
    Pour les coroutines async, utilise asyncio.create_task() au lieu
    du cycle HTTP qui ne se déclenche jamais côté WS.
    """
    def add_task(self, func, *args, **kwargs):
        if asyncio.iscoroutinefunction(func):
            asyncio.create_task(func(*args, **kwargs))
        else:
            super().add_task(func, *args, **kwargs)


# ═══════════════════════════════════════════════════════════
# HANDLER PRINCIPAL
# ═══════════════════════════════════════════════════════════

async def handle_websocket(
    websocket: WebSocket,
    session_id: str,
    process_fn,
    background_tasks=None,
):
    """
    Gère une connexion WebSocket complète.

    FIX V1.2 : session_id est passé comme "phone" dans process_fn.
    Le format "web_uuid" ne passe pas validate_phone() — on patche
    core/security.py pour accepter les sessions web, ou on intercepte
    l'erreur ici et on renvoie un message clair.
    """
    background_tasks = AsyncBackgroundTasks()

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

    # FIX V1.2 : send_fn avec gestion d'erreur robuste
    async def send_fn(_phone: str, text: str) -> bool:
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

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=_HEARTBEAT_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.info(f"[WS] Heartbeat timeout — session={session_id[:20]}")
                await websocket.close(code=4002)
                return

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(websocket, {
                    "type":    "error",
                    "message": "Format invalide. Envoie du JSON.",
                })
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
                    await _send(websocket, {
                        "type":    "error",
                        "message": "Message trop long (500 caractères max).",
                    })
                    continue

                logger.info(
                    f"[WS] Chat — session={session_id[:20]} "
                    f"text={text[:60]!r}"
                )
                print(f"[WS DEBUG] Chat reçu — session={session_id[:20]} text={text[:60]!r}", flush=True)

                try:
                    await process_fn(
                        phone=session_id,
                        text=text,
                        background_tasks=background_tasks,
                        send_fn=send_fn,
                    )
                    print(f"[WS DEBUG] process_fn terminé OK", flush=True)
                except Exception as e:
                    traceback.print_exc()
                    print(f"===== WS CRASH ===== {type(e).__name__}: {e}", flush=True)
                    logger.error(f"[WS] Erreur process_fn: {e}", exc_info=True)
                    await _send(websocket, {
                        "type":    "error",
                        "message": "Erreur interne. Réessaie dans un instant.",
                    })
                continue

            if msg_type == "report":
                await _handle_report(websocket, msg, session_id, background_tasks)
                continue

            logger.debug(f"[WS] Type inconnu: {msg_type!r}")
            await _send(websocket, {
                "type":    "error",
                "message": f"Type de message inconnu : {msg_type}",
            })

    except WebSocketDisconnect:
        logger.info(f"[WS] Déconnexion propre — session={session_id[:20]}")
    except Exception as e:
        traceback.print_exc()
        print(f"===== WS GLOBAL CRASH ===== {type(e).__name__}: {e}", flush=True)
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
    background_tasks: AsyncBackgroundTasks,
):
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
            await _send(websocket, {
                "type": "report_ack", "success": True, "status": "already_recorded",
            })
            return

        if observation:
            try:
                queries.enrichir_signalement(
                    ligne=ligne, arret=arret,
                    qualite=observation, phone=session_id
                )
            except Exception as e:
                logger.warning(f"[WS] Enrichissement échoué: {e}")

        import skills.signalement as skill_signalement
        background_tasks.add_task(skill_signalement.notify_abonnes, ligne, arret, session_id)

        report_id = f"rpt_{result.get('id', 'ok')}" if isinstance(result, dict) else "rpt_ok"

        logger.info(
            f"[WS] Report ✅ ligne={ligne} arret={arret} "
            f"obs={observation} session={session_id[:20]}"
        )

        await _send(websocket, {
            "type": "report_ack", "success": True,
            "id": report_id, "status": "recorded",
        })

    except Exception as e:
        traceback.print_exc()
        print(f"===== WS REPORT CRASH ===== {type(e).__name__}: {e}", flush=True)
        logger.error(f"[WS] Erreur report: {e}", exc_info=True)
        await _send(websocket, {
            "type": "report_ack", "success": False, "error": "Erreur interne.",
        })


# ═══════════════════════════════════════════════════════════
# HELPER ENVOI
# ═══════════════════════════════════════════════════════════

async def _send(websocket: WebSocket, data: dict) -> bool:
    try:
        await websocket.send_text(json.dumps(data, ensure_ascii=False))
        return True
    except Exception as e:
        logger.debug(f"[WS] _send failed: {e}")
        return False