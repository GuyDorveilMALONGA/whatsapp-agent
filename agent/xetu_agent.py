"""
agent/xetu_agent.py — V1.5 (checkpointer PostgreSQL + fallback gracieux)
Agent ReAct LangGraph — cœur de Xëtu.

MIGRATIONS V1.5 depuis V1.4 :
  - Fallback sans checkpointer si la connexion DB échoue
    (pas de persistance d'historique, mais l'agent répond)
  - Log explicite pour diagnostiquer le problème checkpointer
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
_checkpointer_failed = False  # True si le checkpointer a déjà échoué


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

    # Si déjà échoué, ne pas réessayer à chaque message (évite les logs spam)
    # On réessaiera toutes les 60 secondes
    if _checkpointer_failed:
        return None

    try:
        from agent.checkpointer import get_checkpointer
        cp = await get_checkpointer()
        return cp
    except Exception as e:
        _checkpointer_failed = True
        logger.warning(
            f"[xetu_run] Checkpointer indisponible — mode sans historique activé.\n"
            f"  Cause : {type(e).__name__}: {e}\n"
            f"  → Ajoutez DB_PASSWORD dans Railway pour activer la persistance."
        )
        # Réessayer dans 60s
        import asyncio
        asyncio.get_event_loop().call_later(60, _reset_checkpointer_flag)
        return None


def _reset_checkpointer_flag():
    global _checkpointer_failed
    _checkpointer_failed = False
    logger.info("[xetu_run] Checkpointer flag reset — prochaine tentative de connexion.")


async def run(
    message: str,
    phone: str,
    langue: str = "fr",
    history: list = None,
) -> str:
    """
    Point d'entrée unique de Xëtu.
    - Avec checkpointer : historique géré par LangGraph via thread_id=phone.
    - Sans checkpointer (fallback) : agent sans mémoire, mais fonctionnel.
    """
    global _fallback_count

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

    config = {
        "configurable": {
            "phone": phone,
            "thread_id": phone,
        }
    }

    # ── Tentative avec checkpointer ───────────────────────
    checkpointer = await _try_get_checkpointer()

    if checkpointer:
        try:
            agent = _get_agent_with_checkpointer(agent_base, checkpointer, agent_name)
            result = await agent.ainvoke(
                {"messages": [HumanMessage(content=message)]},
                config=config,
            )
            return _extract_response(result)

        except Exception as e:
            if _is_rate_limit_error(e) and agent_name == "groq":
                _fallback_count += 1
                logger.warning(f"[xetu_run] Groq 429 — fallback Gemini (#{_fallback_count})")
                try:
                    agent = _get_agent_with_checkpointer(
                        _agent_gemini_base, checkpointer, "gemini-fallback"
                    )
                    result = await agent.ainvoke(
                        {"messages": [HumanMessage(content=message)]},
                        config=config,
                    )
                    return _extract_response(result)
                except Exception as fallback_err:
                    logger.error(f"[xetu_run] Fallback Gemini échoué: {fallback_err}", exc_info=True)
                    raise fallback_err
            raise

    # ── Fallback SANS checkpointer ────────────────────────
    logger.info(f"[xetu_run] Mode sans checkpointer — agent={agent_name}")

    try:
        result = await agent_base.ainvoke(
            {"messages": [HumanMessage(content=message)]},
            config=config,
        )
        return _extract_response(result)

    except Exception as e:
        if _is_rate_limit_error(e) and agent_name == "groq":
            _fallback_count += 1
            logger.warning(f"[xetu_run] Groq 429 (sans checkpointer) — fallback Gemini (#{_fallback_count})")
            try:
                result = await _agent_gemini_base.ainvoke(
                    {"messages": [HumanMessage(content=message)]},
                    config=config,
                )
                return _extract_response(result)
            except Exception as fallback_err:
                logger.error(f"[xetu_run] Fallback Gemini échoué: {fallback_err}", exc_info=True)
                raise fallback_err
        raise


def _extract_response(result: dict) -> str:
    last_msg = result["messages"][-1]
    response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    if not response or not response.strip():
        logger.warning("[xetu_run] Réponse vide de l'agent !")
        response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"
    logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
    return response