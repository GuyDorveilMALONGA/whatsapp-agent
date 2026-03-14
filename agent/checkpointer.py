"""
agent/checkpointer.py — V1.5
Session Pooler Supabase — IPv4 compatible pour Railway.

FIX V1.5 :
  - Accepte DB_PASSWORD, DBPASSWORD, ou DATABASE_URL (fallback)
  - Reconnexion automatique si la connexion PostgreSQL est perdue
  - Logging explicite si aucune variable n'est trouvée
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
    """Cherche le mot de passe dans toutes les variables possibles."""
    # Priorité 1 : variable explicite
    for key in ("DB_PASSWORD", "DBPASSWORD", "SUPABASE_DB_PASSWORD"):
        val = os.environ.get(key)
        if val:
            logger.info(f"[Checkpointer] Mot de passe trouvé via {key}")
            return val

    # Priorité 2 : extraire depuis DATABASE_URL
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        try:
            parsed = urlparse(db_url)
            if parsed.password:
                logger.info("[Checkpointer] Mot de passe extrait de DATABASE_URL")
                return parsed.password
        except Exception:
            pass

    # Aucune variable trouvée — log toutes les variables DB pour debug
    db_vars = {k: v[:4] + "***" for k, v in os.environ.items()
               if any(x in k.upper() for x in ("DB", "DATABASE", "PG", "SUPABASE"))}
    logger.error(
        f"[Checkpointer] AUCUN mot de passe DB trouvé !\n"
        f"  Variables cherchées : DB_PASSWORD, DBPASSWORD, SUPABASE_DB_PASSWORD, DATABASE_URL\n"
        f"  Variables DB présentes dans l'env : {db_vars}"
    )
    raise RuntimeError(
        "Aucune variable d'environnement pour le mot de passe DB. "
        "Ajoutez DB_PASSWORD dans Railway → Variables."
    )


async def get_checkpointer() -> AsyncPostgresSaver:
    global _checkpointer, _connection

    # Vérifier si la connexion existante est encore vivante
    if _checkpointer is not None and _connection is not None:
        try:
            # Test rapide : la connexion est-elle ouverte ?
            if not _connection.closed:
                return _checkpointer
            logger.warning("[Checkpointer] Connexion fermée — reconnexion...")
        except Exception:
            logger.warning("[Checkpointer] Connexion invalide — reconnexion...")

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
    logger.info("[Checkpointer] PostgreSQL initialisé ✅")
    return _checkpointer