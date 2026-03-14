"""
agent/checkpointer.py — V1.1
Checkpointer PostgreSQL pour LangGraph — persistance Supabase.
"""
import logging
import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Retourne le checkpointer singleton, initialisé au premier appel."""
    global _checkpointer
    if _checkpointer is None:
        from config.settings import DATABASE_URL
        conn = await psycopg.AsyncConnection.connect(
            DATABASE_URL,
            autocommit=True,
        )
        _checkpointer = AsyncPostgresSaver(conn)
        await _checkpointer.setup()
        logger.info("[Checkpointer] PostgreSQL initialisé ✅")
    return _checkpointer