"""
core/queue_manager.py — V2
File d'attente asyncio par session.
Garantit que les écritures Supabase pour le même usager
ne se marchent jamais dessus.

Usage dans main.py :
    async with queue_manager.process(phone):
        await _process_message(phone, text)
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from core.session_manager import get_session_lock

logger = logging.getLogger(__name__)


@asynccontextmanager
async def process(phone: str):
    """
    Context manager qui sérialise le traitement par numéro.

    Exemple :
        async with queue_manager.process(phone):
            await _do_work(phone, text)
    """
    lock = get_session_lock(phone)

    try:
        # Attend que le message précédent de cet usager soit traité
        await asyncio.wait_for(lock.acquire(), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning(f"[Queue] Timeout lock pour {phone[-4:]} — message ignoré")
        raise

    try:
        yield
    finally:
        lock.release()
