"""
agent/checkpointer.py — V1.2
Checkpointer PostgreSQL pour LangGraph — persistance Supabase.

MIGRATIONS V1.2 depuis V1.1 :
  - Paramètres de connexion séparés (pas d'URL) pour éviter les problèmes
    de parsing avec les caractères spéciaux dans le mot de passe
  - prepare_threshold=None obligatoire avec pgbouncer/Supavisor (mode transaction)
  - Mot de passe isolé dans DB_PASSWORD (variable Railway dédiée)
"""
import os
import logging
import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None


async def get_checkpointer() -> AsyncPostgresSaver:
    """Retourne le checkpointer singleton, initialisé au premier appel."""
    global _checkpointer
    if _checkpointer is None:
        conn = await psycopg.AsyncConnection.connect(
            host="aws-0-eu-west-3.pooler.supabase.com",
            port=6543,
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