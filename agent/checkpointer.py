"""
agent/checkpointer.py — V1.6
Session Pooler Supabase — IPv4 compatible pour Railway.

FIX V1.6 :
  - Cherche le mot de passe dans : DB_PASSWORD, DBPASSWORD, DATABASE_URL, etc.
  - Log toutes les variables DB-related si rien trouvé (pour debug Railway)
  - Reconnexion automatique si connexion PostgreSQL perdue
"""
import os
import logging
import psycopg
from urllib.parse import urlparse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_connection: psycopg.AsyncConnection | None = None


def _get_db_password() -> str:
    """Cherche le mot de passe DB dans toutes les sources possibles."""

    # 1. Variables explicites
    for key in ("DB_PASSWORD", "DBPASSWORD", "SUPABASE_DB_PASSWORD",
                "PG_PASSWORD", "POSTGRES_PASSWORD"):
        val = os.environ.get(key)
        if val:
            logger.info(f"[Checkpointer] Mot de passe trouvé via {key}")
            return val

    # 2. Extraire depuis une URL de connexion
    for url_key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        db_url = os.environ.get(url_key, "")
        if db_url and ":" in db_url:
            try:
                parsed = urlparse(db_url)
                if parsed.password:
                    logger.info(f"[Checkpointer] Mot de passe extrait de {url_key}")
                    return parsed.password
            except Exception as e:
                logger.warning(f"[Checkpointer] Impossible de parser {url_key}: {e}")

    # 3. Échec — log utile pour debug
    db_vars = {}
    for k, v in os.environ.items():
        k_up = k.upper()
        if any(x in k_up for x in ("DB", "DATABASE", "PG", "POSTGRES", "SUPABASE", "PASSWORD")):
            db_vars[k] = v[:6] + "***" if len(v) > 6 else "***"

    logger.error(
        f"[Checkpointer] AUCUN mot de passe DB trouvé !\n"
        f"  Variables cherchées : DB_PASSWORD, DBPASSWORD, SUPABASE_DB_PASSWORD, "
        f"PG_PASSWORD, POSTGRES_PASSWORD, DATABASE_URL, SUPABASE_DB_URL, POSTGRES_URL\n"
        f"  Variables pertinentes dans l'env : {db_vars}"
    )
    raise RuntimeError(
        "Aucune variable d'environnement pour le mot de passe DB. "
        "Ajoutez DB_PASSWORD dans Railway -> Variables."
    )


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer, _connection

    # Vérifier si la connexion existante est encore vivante
    if _checkpointer is not None and _connection is not None:
        try:
            if not _connection.closed:
                return _checkpointer
            logger.warning("[Checkpointer] Connexion fermee -- reconnexion...")
        except Exception:
            logger.warning("[Checkpointer] Connexion invalide -- reconnexion...")

        _checkpointer = None
        _connection = None

    # Nouvelle connexion
    password = _get_db_password()

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
    logger.info("[Checkpointer] PostgreSQL initialise OK")
    return _checkpointer