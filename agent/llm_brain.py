"""
agent/llm_brain.py
Le LLM fait UNE seule chose : transformer un contexte préparé
en une phrase naturelle dans la bonne langue.
Il ne détecte pas, ne classe pas, ne cherche pas. Il rédige.

RÈGLE ABSOLUE : Wolof → Gemini UNIQUEMENT. Jamais Groq pour le wolof.
"""
import logging
import httpx
import google.generativeai as genai
from groq import AsyncGroq

from config.settings import (
    GROQ_API_KEY, GEMINI_API_KEY,
    GROQ_MODEL, GEMINI_MODEL,
    LLM_ROUTING, SETU_SOUL
)

logger = logging.getLogger(__name__)

# Init clients
_groq_client = AsyncGroq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)


async def generate_response(
    context: str,
    langue: str,
    history: list[dict] | None = None
) -> str:
    """
    Génère la réponse finale.
    context : tout le contexte préparé (signalements, profil, etc.)
    langue  : 'fr' | 'en' | 'wolof' | 'pulaar' | 'unknown'
    history : liste de {role, content} pour la mémoire de conversation
    """
    provider = LLM_ROUTING.get(langue, "groq")

    prompt = _build_prompt(context, langue, history or [])

    if provider == "gemini":
        return await _call_gemini(prompt)
    else:
        return await _call_groq(prompt)


def _build_prompt(context: str, langue: str, history: list[dict]) -> str:
    langue_label = {
        "fr": "français",
        "en": "anglais",
        "wolof": "wolof (langue naturelle, pas de traduction littérale du français)",
        "pulaar": "pulaar",
        "unknown": "français",
    }.get(langue, "français")

    history_text = ""
    if history:
        lines = []
        for msg in history[-6:]:  # 3 derniers échanges max
            role = "Usager" if msg["role"] == "user" else "Sëtu"
            lines.append(f"{role}: {msg['content']}")
        history_text = "\n".join(lines)

    return f"""{SETU_SOUL}

LANGUE DE RÉPONSE : {langue_label}

{f"HISTORIQUE RÉCENT :{chr(10)}{history_text}{chr(10)}" if history_text else ""}
SITUATION ACTUELLE :
{context}

Rédige la réponse à envoyer à l'usager. 1 à 3 phrases MAX. Naturel et direct."""


async def _call_groq(prompt: str) -> str:
    try:
        response = await _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return "Désolé, une erreur s'est produite. Réessaie dans un moment."


async def _call_gemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        # Fallback français — PAS de fallback Groq wolof
        return "Désolé, service temporairement indisponible. Réessaie dans un moment."
