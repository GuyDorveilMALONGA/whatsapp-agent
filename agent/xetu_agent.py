"""
agent/xetu_agent.py — V1.4 (checkpointer PostgreSQL)
Agent ReAct LangGraph — cœur de Xëtu.

MIGRATIONS V1.4 depuis V1.3 :
  - Checkpointer AsyncPostgresSaver branché sur les deux agents
  - thread_id = phone (persistance par utilisateur)
  - history n'est plus passé manuellement — LangGraph le gère
"""
import logging
import time

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

_fallback_count = 0
_fallback_last_reset = time.time()


def get_fallback_stats() -> dict:
    return {
        "fallback_count": _fallback_count,
        "since": _fallback_last_reset,
    }


_llm_groq = ChatGroq(
    model=GROQ_MODEL,
    temperature=0,
    api_key=GROQ_API_KEY,
    max_tokens=1024,
)

_llm_gemini = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    temperature=0,
    google_api_key=GEMINI_API_KEY,
    max_output_tokens=1024,
)

# Les agents sont créés sans checkpointer ici —
# le checkpointer est injecté au moment de l'appel (async).
_agent_groq_base = create_react_agent(
    model=_llm_groq,
    tools=ALL_TOOLS,
    prompt=SETU_SOUL,
)

_agent_gemini_base = create_react_agent(
    model=_llm_gemini,
    tools=ALL_TOOLS,
    prompt=SETU_SOUL,
)


def _is_rate_limit_error(exc: Exception) -> bool:
    exc_type = type(exc).__name__
    if "RateLimitError" in exc_type:
        return True
    if "429" in str(exc):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause and "RateLimitError" in type(cause).__name__:
        return True
    return False


async def run(
    message: str,
    phone: str,
    langue: str = "fr",
    history: list = None,  # conservé pour compatibilité, ignoré si checkpointer actif
) -> str:
    """
    Point d'entrée unique de Xëtu.
    Avec checkpointer : l'historique est géré par LangGraph via thread_id=phone.
    Sans checkpointer (fallback) : history est utilisé comme avant.
    """
    global _fallback_count

    from agent.checkpointer import get_checkpointer

    # ── Choix de l'agent ─────────────────────────────────
    if langue == "wolof":
        agent_base = _agent_gemini_base
        agent_name = "gemini"
    else:
        agent_base = _agent_groq_base
        agent_name = "groq"

    logger.info(
        f"[xetu_run] langue={langue!r} | phone={phone[:8]}… | agent={agent_name}"
    )

    # ── Config : phone + thread_id pour le checkpointer ──
    config = {
        "configurable": {
            "phone": phone,
            "thread_id": phone,   # LangGraph utilise thread_id pour la persistance
        }
    }

    # ── Tentative avec checkpointer ───────────────────────
    try:
        checkpointer = await get_checkpointer()

        # Recrée l'agent avec le checkpointer si pas encore fait
        agent = _get_agent_with_checkpointer(agent_base, checkpointer, agent_name)

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config=config,
        )
        return _extract_response(result)

    except Exception as e:
        # ── Fallback Gemini si Groq rate limit ───────────
        if agent_name == "groq" and _is_rate_limit_error(e):
            _fallback_count += 1
            logger.warning(
                f"[xetu_run] Groq 429 — fallback Gemini "
                f"(fallback #{_fallback_count})"
            )
            try:
                checkpointer = await get_checkpointer()
                agent = _get_agent_with_checkpointer(
                    _agent_gemini_base, checkpointer, "gemini-fallback"
                )
                result = await agent.ainvoke(
                    {"messages": [HumanMessage(content=message)]},
                    config=config,
                )
                return _extract_response(result)
            except Exception as fallback_err:
                logger.error(
                    f"[xetu_run] Fallback Gemini AUSSI en échec — "
                    f"{type(fallback_err).__name__}: {fallback_err}",
                    exc_info=True,
                )
                raise fallback_err

        logger.error(
            f"[xetu_run] CRASH — {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise


# Cache des agents avec checkpointer (évite de les recréer à chaque appel)
_agents_with_checkpointer: dict = {}


def _get_agent_with_checkpointer(agent_base, checkpointer, name: str):
    """Retourne un agent avec checkpointer, mis en cache par nom."""
    if name not in _agents_with_checkpointer:
        from langgraph.prebuilt import create_react_agent
        if name == "gemini" or name == "gemini-fallback":
            _agents_with_checkpointer[name] = create_react_agent(
                model=_llm_gemini,
                tools=ALL_TOOLS,
                prompt=SETU_SOUL,
                checkpointer=checkpointer,
            )
        else:
            _agents_with_checkpointer[name] = create_react_agent(
                model=_llm_groq,
                tools=ALL_TOOLS,
                prompt=SETU_SOUL,
                checkpointer=checkpointer,
            )
        logger.info(f"[xetu_run] Agent '{name}' créé avec checkpointer ✅")
    return _agents_with_checkpointer[name]


def _extract_response(result: dict) -> str:
    last_msg = result["messages"][-1]
    response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    if not response or not response.strip():
        logger.warning("[xetu_run] Réponse vide de l'agent !")
        response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"
    logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
    return response