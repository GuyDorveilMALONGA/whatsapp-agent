"""
rag/retriever.py — V2.0
Pont entre get_bus_info (tools.py) et la knowledge base Supabase.

MIGRATIONS V2.0 :
  - Remplace l'ancienne version qui importait directement supabase
  - Utilise hybrid_search() depuis rag/search (code existant)
  - retrieve() synchrone pour compatibilité avec get_bus_info tool
  - Zéro nouveau code métier — juste un adaptateur
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


def retrieve(query: str, ligne: str | None = None, limit: int = 3) -> str | None:
    """
    Recherche dans la knowledge base transport.
    Retourne un texte formaté ou None si rien trouvé.
    Synchrone — appelé depuis get_bus_info tool.
    """
    try:
        from config.settings import TENANT_ID
        from rag.search import hybrid_search, format_context

        # hybrid_search est async — on l'exécute dans la boucle courante
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Contexte async (LangGraph) — on crée une coroutine directe
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        hybrid_search(query, TENANT_ID, limit)
                    )
                    chunks = future.result(timeout=5)
            else:
                chunks = loop.run_until_complete(
                    hybrid_search(query, TENANT_ID, limit)
                )
        except Exception:
            chunks = []

        if not chunks:
            return None

        return format_context(chunks) or None

    except Exception as e:
        logger.warning(f"[retriever] erreur: {e}")
        return None