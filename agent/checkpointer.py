"""
agent/checkpointer.py — V1.4
Session Pooler Supabase — IPv4 compatible pour Railway.
"""
import os
import logging
import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer
    if _checkpointer is None:
        conn = await psycopg.AsyncConnection.connect(
            host="aws-1-eu-west-2.pooler.supabase.com",
            port=5432,
            dbname="postgres",
            user="postgres.hhsahrscdepivpvjoouj",
            password=os.environ["DB_PASSWORD"],
            sslmode="require",
            autocommit=True,
            prepare_threshold=None,
        )
        _checkpointer = AsyncPostgresSaver(conn)
        await _checkpointer.setup()
        logger.info("[Checkpointer] PostgreSQL initialisé ✅")
    return _checkpointer