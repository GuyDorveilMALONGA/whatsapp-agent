from db.supabase import supabase
import os


async def hybrid_search(query: str, tenant_id: str, limit: int = 3) -> list:
    """Recherche dans la knowledge base transport"""
    try:
        result = supabase.rpc(
            "search_knowledge_base",
            {
                "query_text": query,
                "p_tenant_id": tenant_id,
                "match_limit": limit
            }
        ).execute()

        if result.data:
            return result.data

        result = supabase.table("knowledge_base")\
            .select("content, metadata, source_type")\
            .eq("tenant_id", tenant_id)\
            .limit(limit)\
            .execute()

        return result.data or []

    except Exception as e:
        print(f"Erreur RAG search: {e}")
        return []


async def search_signalements_recents(ligne: str, tenant_id: str, limit: int = 3) -> list:
    """Cherche les signalements récents d'une ligne"""
    try:
        result = supabase.table("signalements")\
            .select("ligne, position, timestamp")\
            .eq("tenant_id", tenant_id)\
            .eq("ligne", ligne)\
            .eq("valide", True)\
            .order("timestamp", desc=True)\
            .limit(limit)\
            .execute()
        return result.data or []
    except Exception as e:
        print(f"Erreur search signalements: {e}")
        return []


async def search_arrets(query: str, limit: int = 5) -> list:
    """Cherche des arrêts par nom"""
    try:
        result = supabase.table("arrets")\
            .select("nom, ligne_numero, direction")\
            .ilike("nom", f"%{query}%")\
            .limit(limit)\
            .execute()
        return result.data or []
    except Exception as e:
        print(f"Erreur search arrêts: {e}")
        return []


def format_context(chunks: list) -> str:
    """Formate les chunks RAG pour le prompt"""
    if not chunks:
        return ""
    context = "INFORMATIONS DISPONIBLES :\n"
    for i, chunk in enumerate(chunks, 1):
        content = chunk.get("content", "")
        source = chunk.get("source_type", "")
        if content:
            context += f"\n[{i}]"
            if source:
                context += f" ({source})"
            context += f" {content}\n"
    return context


def format_signalements(signalements: list, ligne: str) -> str:
    """Formate les signalements récents pour le prompt"""
    if not signalements:
        return f"Aucun signalement récent pour la ligne {ligne}."
    context = f"DERNIERS SIGNALEMENTS — Bus {ligne} :\n"
    for s in signalements:
        context += f"  • {s.get('position', '?')} — {s.get('timestamp', '?')}\n"
    return context
