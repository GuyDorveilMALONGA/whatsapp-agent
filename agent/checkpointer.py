"""
agent/checkpointer.py — V2.0
Session Pooler Supabase — connexion unique partagée.

MIGRATIONS V2.0 depuis V1.7 :
  - FIX BUG-C4 : Race condition fast path supprimée.
    L'ancienne version vérifiait _connection.closed HORS du lock →
    deux coroutines pouvaient passer le fast path simultanément,
    l'une ferme la connexion pendant que l'autre l'utilise → crash.
    Fix : plus de fast path hors lock. On entre toujours dans le lock,
    mais on sort immédiatement si la connexion est saine (_is_ready flag).
    Le flag est mis à False atomiquement dans le lock dès qu'un problème
    est détecté → une seule coroutine reconstruit la connexion.
  - _is_ready : booléen simple, mis à jour uniquement dans le lock.
  - Reconnexion automatique si connexion perdue (inchangé).
  - Cherche DB_PASSWORD dans toutes les variantes (inchangé).
"""
import os
import asyncio
import logging
import psycopg
from urllib.parse import urlparse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_connection:   psycopg.AsyncConnection | None = None
_is_ready:     bool = False   # True uniquement quand connexion vérifiée dans le lock
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
    global _checkpointer, _connection, _is_ready

    # Toujours entrer dans le lock — pas de fast path hors lock (FIX BUG-C4)
    async with _lock:

        # Vérifier l'état de la connexion dans le lock (atomique)
        if _is_ready and _checkpointer is not None and _connection is not None:
            try:
                if not _connection.closed:
                    return _checkpointer
            except Exception:
                pass
            # Connexion détectée comme morte — on reconstruit
            _is_ready = False
            logger.warning("[Checkpointer] Connexion perdue — reconnexion...")

        # Fermer proprement l'ancienne connexion
        if _connection is not None:
            try:
                await _connection.close()
            except Exception:
                pass
            _connection = None
            _checkpointer = None
            _is_ready = False

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
        _is_ready = True
        logger.info("[Checkpointer] PostgreSQL initialisé ✅")
        return _checkpointer