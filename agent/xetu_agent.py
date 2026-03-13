"""
agent/xetu_agent.py — V1.1 (debug)
Agent ReAct LangGraph — cœur de Xëtu.

LLM routing :
  - Wolof  → Gemini 2.0 Flash
  - Autres → Llama 4 Scout via Groq
"""
from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

from config.settings import (
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    SETU_SOUL,
)
from agent.tools import ALL_TOOLS

# ── LLM Groq — Llama 4 Scout (FR, EN, Pulaar, unknown) ───
_llm_groq = ChatGroq(
    model=GROQ_MODEL,
    temperature=0,
    api_key=GROQ_API_KEY,
    max_tokens=1024,
)

# ── LLM Gemini — pour le Wolof ────────────────────────────
_llm_gemini = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
    google_api_key=GEMINI_API_KEY,
    max_output_tokens=1024,
)

# ── Agents — un par LLM, même tools, même prompt ─────────
_agent_groq = create_react_agent(
    model=_llm_groq,
    tools=ALL_TOOLS,
    prompt=SETU_SOUL,
)

_agent_gemini = create_react_agent(
    model=_llm_gemini,
    tools=ALL_TOOLS,
    prompt=SETU_SOUL,
)


async def run(message: str, phone: str, langue: str = "fr", history: list = None) -> str:
    """
    Point d'entrée unique de Xëtu.
    Remplace route_async() de agent/router.py.

    Args:
        message : Message brut de l'utilisateur
        phone   : Numéro de téléphone E.164
        langue  : Langue détectée en amont ('wolof', 'fr', 'en', ...)
        history : Historique [{"role": "user/assistant", "content": "..."}]

    Returns:
        Réponse finale en string
    """
    import traceback
    import logging
    logger = logging.getLogger(__name__)

    try:
        agent = _agent_gemini if langue == "wolof" else _agent_groq

        messages = list(history or [])
        messages.append({"role": "user", "content": message})

        logger.info(f"[xetu_run] langue={langue!r} | messages={len(messages)} | phone={phone[:8]}...")

        result = await agent.ainvoke(
            {"messages": messages},
            config={"configurable": {"phone": phone}},
        )

        response = result["messages"][-1].content
        logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
        return response

    except Exception as e:
        traceback.print_exc()
        logger.error(f"[xetu_run] CRASH — {type(e).__name__}: {e}", exc_info=True)
        raise