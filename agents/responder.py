from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

LANGUAGE_NAMES = {
    "wo": "Wolof",
    "ff": "Pulaar",
    "fr": "Français",
    "en": "Anglais",
    "other": "Français"
}

SYSTEM_PROMPT = """Tu es un assistant service client professionnel et chaleureux pour {business_name}.

RÈGLES ABSOLUES :
1. Réponds TOUJOURS en {language_name} — c'est la langue du client
2. Sois chaleureux, empathique et professionnel
3. Base tes réponses UNIQUEMENT sur les informations fournies dans le contexte
4. Si tu ne sais pas, dis-le honnêtement et propose de vérifier
5. Ne jamais inventer des prix, des produits ou des politiques
6. Garde tes réponses concises — max 3 paragraphes courts
7. Tu comprends le contexte culturel africain — adapte ton ton

CONTEXTE DISPONIBLE :
{rag_context}

Si le contexte est vide, réponds de façon générale et propose d'avoir plus d'informations."""

async def generate_response(
    message: str,
    history: list,
    language: str,
    intent: str,
    rag_context: str,
    business_name: str,
    is_escalated: bool = False
) -> dict:
    """Génère une réponse via Groq avec contexte RAG"""

    if is_escalated:
        escalation_messages = {
            "fr": "Je comprends votre demande. Je vous transfère vers un de nos agents qui pourra mieux vous aider. Merci de patienter quelques instants.",
            "wo": "Mangi xam sa xam-xam. Dinaa la jëfandikoo ak benn agent bu ci kanam. Jërejëf ci ci koom.",
            "ff": "Mi faami ko mbii-ɗaa. Mi yettoo ma e koolol ɗiɗaaɓe ngalɗa no moƴƴi.",
            "en": "I understand your request. I'm transferring you to one of our agents who can better assist you. Please hold on."
        }
        reply = escalation_messages.get(language, escalation_messages["fr"])
        return {"reply": reply, "confidence": 1.0}

    language_name = LANGUAGE_NAMES.get(language, "Français")

    system = SYSTEM_PROMPT.format(
        business_name=business_name,
        language_name=language_name,
        rag_context=rag_context if rag_context else "Aucune information spécifique disponible."
    )

    # Construit l'historique pour le contexte
    messages = [{"role": "system", "content": system}]
    for msg in history[-8:]:  # 8 derniers messages max
        messages.append({
            "role": msg["role"] if msg["role"] in ["user", "assistant"] else "assistant",
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": message})

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=400,
            temperature=0.7
        )

        reply = response.choices[0].message.content

        # Score de confiance basique
        confidence = 0.9 if rag_context else 0.6

        return {"reply": reply, "confidence": confidence}

    except Exception as e:
        print(f"Erreur génération réponse: {e}")
        fallback = {
            "fr": "Désolé, je rencontre une difficulté technique. Veuillez réessayer dans quelques instants.",
            "wo": "Baal ma, am na dëgg ci teknik. Jëkkal ci kanam.",
            "en": "Sorry, I'm experiencing a technical issue. Please try again in a moment."
        }
        return {"reply": fallback.get(language, fallback["fr"]), "confidence": 0.0}
