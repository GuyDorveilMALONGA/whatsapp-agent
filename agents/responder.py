from groq import Groq
import google.generativeai as genai
import os

# Clients
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

LANGUAGE_NAMES = {
    "wo": "Wolof",
    "ff": "Pulaar",
    "fr": "Français",
    "en": "Anglais",
    "other": "Français"
}

SYSTEM_PROMPT_GROQ = """Tu es un assistant service client professionnel et chaleureux pour {business_name}.

RÈGLES ABSOLUES :
1. Réponds TOUJOURS en {language_name}
2. Sois chaleureux, empathique et professionnel
3. Base tes réponses UNIQUEMENT sur les informations du contexte
4. Si tu ne sais pas, dis-le honnêtement
5. Ne jamais inventer des prix ou des produits
6. Garde tes réponses concises — max 3 paragraphes courts
7. Tu comprends le contexte culturel africain

CONTEXTE DISPONIBLE :
{rag_context}"""

SYSTEM_PROMPT_WOLOF = """Yow nga ci am solo ci ndimbal client yi ci {business_name}.

YËGËL YI DAFA WÓOR :
1. TËRALAL ci Wolof bu baax — Wolof wu dëgg, moo tax nga am solo
2. Nob nit ki, jàmm ak ngelaw mooy njëkk
3. Dafa waral nga donn ci xibaar yi nga am ci kàddu bi
4. Bu xamul, wax ko bu dëgg — bul fàtte dara
5. Bul defar jëf bu amul dëgg — prix walla xam-xam bu amul
6. Tontu ci yëgël yu jëm ci réer Afrique — xam nit yu Senegaal

XIBAAR YI ANA :
{rag_context}

JËFANDIKOO WOLOF BU DËGG :
- Salutation : "Salaam Aleekum", "Na nga def", "Mbaa mu ngi fi rek"
- Nob : "Jërejëf", "Yëgël na la ko", "Waaw waaw"
- Bul xam : "Duma ko xam, waaye dinaa ko leegi leegi"
- Jaay : "Naka nga bëgg ?", "Ndax dëgg naa la ?"
- Xam-xam : "Mangi fi ngir sa ndimbal"
"""

async def generate_response(
    message: str,
    history: list,
    language: str,
    intent: str,
    rag_context: str,
    business_name: str,
    is_escalated: bool = False
) -> dict:

    if is_escalated:
        escalation_messages = {
            "fr": "Je comprends votre demande. Je vous transfère vers un de nos agents qui pourra mieux vous aider. Merci de patienter.",
            "wo": "Yëgël naa la. Dinaa la jëfandikoo ak doom agent bu ci kanam ngir ndimbal la bu baax. Jërejëf ci ci koom.",
            "ff": "Mi faami ko mbii-ɗaa. Mi yettoo ma e koolol ɗiɗaaɓe.",
            "en": "I understand your request. I'm transferring you to one of our agents. Please hold on."
        }
        reply = escalation_messages.get(language, escalation_messages["fr"])
        return {"reply": reply, "confidence": 1.0}

    # ── Wolof → Gemini ────────────────────────────────────────
    if language == "wo":
        return await generate_wolof_response(
            message=message,
            history=history,
            rag_context=rag_context,
            business_name=business_name
        )

    # ── Autres langues → Groq ─────────────────────────────────
    return await generate_groq_response(
        message=message,
        history=history,
        language=language,
        rag_context=rag_context,
        business_name=business_name
    )


async def generate_wolof_response(
    message: str,
    history: list,
    rag_context: str,
    business_name: str
) -> dict:
    """Génère une réponse en Wolof via Google Gemini"""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")

        system = SYSTEM_PROMPT_WOLOF.format(
            business_name=business_name,
            rag_context=rag_context if rag_context else "Xibaar amul ci kàddu bi."
        )

        # Construit l'historique
        history_text = ""
        for msg in history[-6:]:
            role = "Client" if msg["role"] == "user" else "Agent"
            history_text += f"{role}: {msg['content']}\n"

        prompt = f"""{system}

YËGËLAM YI JIITU :
{history_text}

Client: {message}
Agent (ci Wolof bu dëgg):"""

        response = model.generate_content(prompt)
        reply = response.text.strip()
        confidence = 0.9 if rag_context else 0.65

        return {"reply": reply, "confidence": confidence}

    except Exception as e:
        print(f"Erreur Gemini Wolof: {e}")
        # Fallback vers Groq si Gemini échoue
        return await generate_groq_response(
            message=message,
            history=history,
            language="wo",
            rag_context=rag_context,
            business_name=business_name
        )


async def generate_groq_response(
    message: str,
    history: list,
    language: str,
    rag_context: str,
    business_name: str
) -> dict:
    """Génère une réponse via Groq pour Français, Anglais, Pulaar"""
    language_name = LANGUAGE_NAMES.get(language, "Français")

    system = SYSTEM_PROMPT_GROQ.format(
        business_name=business_name,
        language_name=language_name,
        rag_context=rag_context if rag_context else "Aucune information spécifique disponible."
    )

    messages = [{"role": "system", "content": system}]
    for msg in history[-8:]:
        messages.append({
            "role": msg["role"] if msg["role"] in ["user", "assistant"] else "assistant",
            "content": msg["content"]
        })
    messages.append({"role": "user", "content": message})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=400,
            temperature=0.7
        )
        reply = response.choices[0].message.content
        confidence = 0.9 if rag_context else 0.6
        return {"reply": reply, "confidence": confidence}

    except Exception as e:
        print(f"Erreur Groq: {e}")
        fallback = {
            "fr": "Désolé, je rencontre une difficulté technique. Veuillez réessayer.",
            "wo": "Baal ma, am na dëgg ci teknik. Jëkkal.",
            "en": "Sorry, I'm experiencing a technical issue. Please try again."
        }
        return {"reply": fallback.get(language, fallback["fr"]), "confidence": 0.0}
