"""
agent/xetu_agent.py — V1.6 (fix Groq tool calls + fallback robuste)
Agent ReAct LangGraph — cœur de Xëtu.

MIGRATIONS V1.6 depuis V1.5 :
  - _is_retryable_error attrape aussi BadRequestError/tool_use_failed
    → Quand Groq/Llama génère un tool call mal formaté, on retry avec Gemini
  - Fallback sans checkpointer fonctionnel
  - Code factorisé via _invoke_agent()
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
_checkpointer_failed = False


def get_fallback_stats() -> dict:
    return {
        "fallback_count": _fallback_count,
        "since": _fallback_last_reset,
    }


# ── LLMs ──────────────────────────────────────────────────

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

# Agents SANS checkpointer (fallback / base)
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


def _is_retryable_error(exc: Exception) -> bool:
    """Détecte les erreurs Groq qui justifient un fallback Gemini."""
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # Rate limit
    if "RateLimitError" in exc_type or "429" in str(exc):
        return True

    # Tool call format error — Groq/Llama génère du XML au lieu de JSON
    if "badrequesterror" in exc_type.lower():
        if "tool_use_failed" in exc_str or "tool call validation" in exc_str:
            return True

    # Cause chaînée
    cause = getattr(exc, "__cause__", None)
    if cause and _is_retryable_error(cause):
        return True

    return False


# Cache des agents avec checkpointer
_agents_with_checkpointer: dict = {}


def _get_agent_with_checkpointer(agent_base, checkpointer, name: str):
    """Retourne un agent avec checkpointer, mis en cache par nom."""
    if name not in _agents_with_checkpointer:
        if name in ("gemini", "gemini-fallback"):
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


async def _try_get_checkpointer():
    """Tente d'obtenir le checkpointer. Retourne None si impossible."""
    global _checkpointer_failed

    if _checkpointer_failed:
        return None

    try:
        from agent.checkpointer import get_checkpointer
        cp = await get_checkpointer()
        return cp
    except Exception as e:
        _checkpointer_failed = True
        logger.warning(
            f"[xetu_run] Checkpointer indisponible — mode sans historique.\n"
            f"  Cause : {type(e).__name__}: {e}"
        )
        import asyncio
        asyncio.get_event_loop().call_later(60, _reset_checkpointer_flag)
        return None


def _reset_checkpointer_flag():
    global _checkpointer_failed
    _checkpointer_failed = False
    logger.info("[xetu_run] Checkpointer flag reset — prochaine tentative.")


async def _invoke_agent(agent, message: str, config: dict) -> str:
    """Invoque un agent et extrait la réponse."""
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )
    return _extract_response(result)


async def run(
    message: str,
    phone: str,
    langue: str = "fr",
    history: list = None,
) -> str:
    """
    Point d'entrée unique de Xëtu.
    - Avec checkpointer : historique géré par LangGraph.
    - Sans checkpointer : agent sans mémoire, mais fonctionnel.
    - Si Groq échoue (rate limit OU tool call error) : fallback Gemini.
    """
    global _fallback_count

    # ── Choix de l'agent ─────────────────────────────────
    if langue == "wolof":
        agent_base = _agent_gemini_base
        agent_name = "gemini"
    else:
        agent_base = _agent_groq_base
        agent_name = "groq"

    logger.info(f"[xetu_run] langue={langue!r} | phone={phone[:8]}… | agent={agent_name}")

    config = {
        "configurable": {
            "phone": phone,
            "thread_id": phone,
        }
    }

    # ── Tentative avec checkpointer ───────────────────────
    checkpointer = await _try_get_checkpointer()

    if checkpointer:
        agent = _get_agent_with_checkpointer(agent_base, checkpointer, agent_name)
        try:
            return await _invoke_agent(agent, message, config)
        except Exception as e:
            if _is_retryable_error(e) and agent_name == "groq":
                _fallback_count += 1
                logger.warning(
                    f"[xetu_run] Groq erreur → fallback Gemini (#{_fallback_count}): "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )
                try:
                    fallback = _get_agent_with_checkpointer(
                        _agent_gemini_base, checkpointer, "gemini-fallback"
                    )
                    return await _invoke_agent(fallback, message, config)
                except Exception as fb_err:
                    logger.error(f"[xetu_run] Fallback Gemini échoué: {fb_err}", exc_info=True)
                    raise fb_err
            raise

    # ── Fallback SANS checkpointer ────────────────────────
    logger.info(f"[xetu_run] Mode sans checkpointer — agent={agent_name}")

    try:
        return await _invoke_agent(agent_base, message, config)
    except Exception as e:
        if _is_retryable_error(e) and agent_name == "groq":
            _fallback_count += 1
            logger.warning(
                f"[xetu_run] Groq erreur (no-cp) → fallback Gemini (#{_fallback_count}): "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            try:
                return await _invoke_agent(_agent_gemini_base, message, config)
            except Exception as fb_err:
                logger.error(f"[xetu_run] Fallback Gemini échoué: {fb_err}", exc_info=True)
                raise fb_err
        raise


def _extract_response(result: dict) -> str:
    last_msg = result["messages"][-1]
    response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    if not response or not response.strip():
        logger.warning("[xetu_run] Réponse vide de l'agent !")
        response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"
    logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
    return response