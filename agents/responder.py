from groq import Groq
import google.generativeai as genai
import os

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

LANGUAGE_NAMES = {
    "wo": "Wolof",
    "ff": "Pulaar",
    "fr": "Français",
    "en": "Anglais",
    "other": "Français"
}

SYSTEM_PROMPT_GROQ = """Tu es Sëtu — assistant transport intelligent pour Dakar, disponible sur WhatsApp.

TON RÔLE :
- Aider les usagers des bus Dem Dikk à Dakar
- Informer sur les positions des bus en temps réel (basé sur les signalements communautaires)
- Encourager les gens à signaler les bus qu'ils voient

RÈGLES :
1. Réponds TOUJOURS en {language_name}
2. Sois chaleureux, concis — comme un ami dakarois
3. Base tes réponses sur le contexte disponible
4. Si tu ne sais pas la position d'un bus, dis-le honnêtement
5. Encourage toujours à signaler : "Quand tu vois le bus, envoie *Bus X à [arrêt]*"
6. Maximum 3 paragraphes courts — on est sur WhatsApp

CONTEXTE DISPONIBLE :
{rag_context}"""

SYSTEM_PROMPT_WOLOF = """Yow dafa am solo ci Sëtu — agent transport Dakar ci WhatsApp.

SA LIGGÉEY :
- Ndimbal nit yi ci bus Dem Dikk yi Dakar
- Wax fii bu bus bi ëpp ci sëñ wi nit yi dëkkante
- Jéggël nit yi nangu signalement yi def

YËGËL :
1. TËRALAL ci Wolof bu dëgg ak bu yomb
2. Nob nit ki, am jàmm — yëgël bu baax
3. Bul daw ci xam-xam bu amul
4. Jéggël nit ki nangu signalement yi def
5. Max 3 paragraphe — fi ngi ci WhatsApp

XIBAAR YI ANA :
{rag_context}"""


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
            "fr": "Je comprends votre demande. Je transmets à notre équipe qui vous contactera rapidement. Merci de votre patience 🙏",
            "wo": "Yëgël naa la. Dinaa la jëfandikoo ak team bi ngir ndimbal la bu baax. Jërejëf ci ci koom 🙏",
            "ff": "Mi faami ko mbii-ɗaa. Mi yettoo ma e koolol ɗiɗaaɓe 🙏",
            "en": "I understand your request. I'm forwarding this to our team who will contact you shortly. Thank you 🙏"
        }
        reply = escalation_messages.get(language, escalation_messages["fr"])
        return {"reply": reply, "confidence": 1.0}

    if language == "wo":
        return await generate_wolof_response(message, history, rag_context, business_name)

    return await generate_groq_response(message, history, language, rag_context, business_name)


async def generate_wolof_response(message, history, rag_context, business_name):
    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        system = SYSTEM_PROMPT_WOLOF.format(
            rag_context=rag_context if rag_context else "Xibaar amul ci kàddu bi."
        )
        history_text = ""
        for msg in history[-6:]:
            role = "Nit" if msg["role"] == "user" else "Sëtu"
            history_text += f"{role}: {msg['content']}\n"

        prompt = f"{system}\n\nYËGËLAM YI JIITU :\n{history_text}\nNit: {message}\nSëtu (ci Wolof):"
        response = model.generate_content(prompt)
        confidence = 0.9 if rag_context else 0.65
        return {"reply": response.text.strip(), "confidence": confidence}

    except Exception as e:
        print(f"Erreur Gemini: {e}")
        return await generate_groq_response(message, history, "wo", rag_context, business_name)


async def generate_groq_response(message, history, language, rag_context, business_name):
    language_name = LANGUAGE_NAMES.get(language, "Français")
    system = SYSTEM_PROMPT_GROQ.format(
        language_name=language_name,
        rag_context=rag_context if rag_context else "Aucun signalement récent disponible."
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
            "fr": "Désolé, je rencontre une difficulté technique. Réessayez dans un instant 🙏",
            "wo": "Baal ma, am na dëgg ci teknik. Jëkkal ci kanam 🙏",
            "en": "Sorry, I'm experiencing a technical issue. Please try again 🙏"
        }
        return {"reply": fallback.get(language, fallback["fr"]), "confidence": 0.0}
