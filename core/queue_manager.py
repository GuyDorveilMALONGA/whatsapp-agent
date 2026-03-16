"""
core/queue_manager.py — V3
File d'attente par session — compatible locks Redis et asyncio.

MIGRATIONS V3 depuis V2 :
  - FIX BUG-C5 : get_session_lock() retourne maintenant un objet
    _RedisLock ou _LocalLock avec .acquire()/.release() async.
    L'ancienne version appelait lock.acquire() directement sur un
    asyncio.Lock — incompatible avec la nouvelle interface.
  - Timeout conservé à 30s (défini dans _LOCK_TIMEOUT de session_manager).
"""
import logging
from contextlib import asynccontextmanager
from core.session_manager import get_session_lock

logger = logging.getLogger(__name__)


@asynccontextmanager
async def process(phone: str):
    """
    Context manager qui sérialise le traitement par numéro.
    Utilise Redis si disponible (multi-worker), asyncio sinon.

    Usage :
        async with queue_manager.process(phone):
            await _do_work(phone, text)
    """
    lock = get_session_lock(phone)
    acquired = await lock.acquire()
    if not acquired:
        logger.warning(f"[Queue] Timeout lock pour {phone[-4:]} — message ignoré")
        raise TimeoutError(f"Lock timeout pour {phone[-4:]}")
    try:
        yield
    finally:
        await lock.release()