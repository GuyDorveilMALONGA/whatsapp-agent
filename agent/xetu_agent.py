"""
agent/xetu_agent.py — V1.2 (fix)
Agent ReAct LangGraph — cœur de Xëtu.

LLM routing :
  - Wolof  → Gemini 2.0 Flash
  - Autres → Llama 4 Scout via Groq

FIX V1.2 :
  - Conversion history → messages LangChain (HumanMessage/AIMessage)
  - Gestion robuste des formats history hétérogènes (Supabase, dict, etc.)
  - Logging renforcé pour tracer les crashs
"""
import logging
import traceback

from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage

from config.settings import (
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    SETU_SOUL,
)
from agent.tools import ALL_TOOLS

logger = logging.getLogger(__name__)

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


# ══════════════════════════════════════════════════════════
# Conversion history Supabase → messages LangChain
# ══════════════════════════════════════════════════════════

def _convert_history(history: list | None) -> list:
    """
    Convertit l'historique (format Supabase ou dict) en objets
    HumanMessage / AIMessage compatibles LangGraph.

    Accepte :
      - [{"role": "user", "content": "..."}, ...]
      - [{"role": "assistant", "content": "..."}, ...]
      - Dicts Supabase avec clés supplémentaires (langue, created_at, etc.)
    """
    if not history:
        return []

    messages = []
    for msg in history:
        # Extraire role et content — tolérant aux formats variés
        role = msg.get("role", "").lower().strip()
        content = msg.get("content", "")

        if not content or not isinstance(content, str):
            continue  # Skip les messages vides ou malformés

        content = content.strip()
        if not content:
            continue

        if role in ("user", "human"):
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai", "bot"):
            messages.append(AIMessage(content=content))
        # Skip les rôles inconnus (system, tool, etc.) — on ne les renvoie pas

    return messages


# ══════════════════════════════════════════════════════════
# Point d'entrée unique
# ══════════════════════════════════════════════════════════

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
    try:
        agent = _agent_gemini if langue == "wolof" else _agent_groq

        # ── Conversion history → LangChain messages ──────────
        messages = _convert_history(history)
        messages.append(HumanMessage(content=message))

        logger.info(
            f"[xetu_run] langue={langue!r} | messages={len(messages)} "
            f"| phone={phone[:8]}… | agent={'gemini' if langue == 'wolof' else 'groq'}"
        )

        result = await agent.ainvoke(
            {"messages": messages},
            config={"configurable": {"phone": phone}},
        )

        # ── Extraire la réponse ──────────────────────────────
        last_msg = result["messages"][-1]
        response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

        # Sécurité : si la réponse est vide, message par défaut
        if not response or not response.strip():
            logger.warning("[xetu_run] Réponse vide de l'agent !")
            response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"

        logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
        return response

    except Exception as e:
        traceback.print_exc()
        logger.error(f"[xetu_run] CRASH — {type(e).__name__}: {e}", exc_info=True)
        raise