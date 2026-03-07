from db.supabase import supabase
from groq import Groq
import os
import json

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

async def get_embedding(text: str) -> list:
    """Génère un embedding via un modèle simple"""
    # Pour le MVP on utilise une approche légère
    # En production: remplacer par nomic-embed-text ou OpenAI embeddings
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "Réponds UNIQUEMENT avec les 10 mots-clés les plus importants de ce texte, séparés par des virgules. Rien d'autre."
                },
                {"role": "user", "content": text}
            ],
            max_tokens=50,
            temperature=0
        )
        return response.choices[0].message.content.strip()
    except:
        return text

async def hybrid_search(query: str, tenant_id: str, limit: int = 3) -> list:
    """
    Recherche hybride : full-text dans la knowledge_base du tenant
    Retourne les chunks les plus pertinents
    """
    try:
        # Recherche full-text PostgreSQL
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

        # Fallback : recherche simple si la fonction RPC n'existe pas encore
        result = supabase.table("knowledge_base")\
            .select("content, metadata, source_type")\
            .eq("tenant_id", tenant_id)\
            .limit(limit)\
            .execute()

        return result.data or []

    except Exception as e:
        print(f"Erreur RAG search: {e}")
        return []

def format_context(chunks: list) -> str:
    """Formate les chunks RAG pour l'injection dans le prompt"""
    if not chunks:
        return ""

    context = "INFORMATIONS DISPONIBLES :\n"
    for i, chunk in enumerate(chunks, 1):
        context += f"\n[{i}] {chunk.get('content', '')}\n"

    return context
