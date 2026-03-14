"""
agent/checkpointer.py — V1.0
Checkpointer PostgreSQL pour LangGraph — persistance Supabase.
"""
import logging
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Retourne le checkpointer singleton, initialisé au premier appel."""
    global _checkpointer
    if _checkpointer is None:
        from config.settings import DATABASE_URL
        _checkpointer = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
        await _checkpointer.setup()
        logger.info("[Checkpointer] PostgreSQL initialisé ✅")
    return _checkpointer