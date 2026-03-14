"""
agent/checkpointer.py — V1.7
Session Pooler Supabase — connexion unique partagée.

FIX V1.7 :
  - asyncio.Lock pour empêcher les connexions concurrentes
    (Telegram + WebSocket simultanés → une seule connexion)
  - Reconnexion automatique si connexion perdue
  - Cherche DB_PASSWORD dans toutes les variantes possibles
"""
import os
import asyncio
import logging
import psycopg
from urllib.parse import urlparse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_connection: psycopg.AsyncConnection | None = None
_lock = asyncio.Lock()


def _get_db_password() -> str:
    """Cherche le mot de passe DB dans toutes les sources possibles."""
    for key in ("DB_PASSWORD", "DBPASSWORD", "SUPABASE_DB_PASSWORD",
                "PG_PASSWORD", "POSTGRES_PASSWORD"):
        val = os.environ.get(key)
        if val:
            logger.info(f"[Checkpointer] Mot de passe trouvé via {key}")
            return val

    for url_key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        db_url = os.environ.get(url_key, "")
        if db_url and ":" in db_url:
            try:
                parsed = urlparse(db_url)
                if parsed.password:
                    logger.info(f"[Checkpointer] Mot de passe extrait de {url_key}")
                    return parsed.password
            except Exception:
                pass

    db_vars = {}
    for k, v in os.environ.items():
        k_up = k.upper()
        if any(x in k_up for x in ("DB", "DATABASE", "PG", "POSTGRES", "SUPABASE", "PASSWORD")):
            db_vars[k] = v[:6] + "***" if len(v) > 6 else "***"
    logger.error(
        f"[Checkpointer] AUCUN mot de passe DB trouvé !\n"
        f"  Variables pertinentes : {db_vars}"
    )
    raise RuntimeError("DB_PASSWORD manquant dans Railway → Variables.")


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer, _connection

    # Fast path — connexion déjà active, pas besoin du lock
    if _checkpointer is not None and _connection is not None:
        try:
            if not _connection.closed:
                return _checkpointer
        except Exception:
            pass

    # Slow path — une seule coroutine crée la connexion
    async with _lock:
        # Re-check après acquisition du lock (une autre coroutine a pu créer entre-temps)
        if _checkpointer is not None and _connection is not None:
            try:
                if not _connection.closed:
                    return _checkpointer
            except Exception:
                pass

        # Fermer proprement l'ancienne connexion si elle existe
        if _connection is not None:
            try:
                await _connection.close()
            except Exception:
                pass
            _connection = None
            _checkpointer = None

        password = _get_db_password()

        logger.info("[Checkpointer] Création connexion PostgreSQL...")
        _connection = await psycopg.AsyncConnection.connect(
            host="aws-1-eu-west-2.pooler.supabase.com",
            port=5432,
            dbname="postgres",
            user="postgres.hhsahrscdepivpvjoouj",
            password=password,
            sslmode="require",
            autocommit=True,
            prepare_threshold=None,
        )
        _checkpointer = AsyncPostgresSaver(_connection)
        await _checkpointer.setup()
        logger.info("[Checkpointer] PostgreSQL initialisé ✅")
        return _checkpointer