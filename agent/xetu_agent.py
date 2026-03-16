"""
agent/xetu_agent.py — V1.9
Agent ReAct LangGraph — cœur de Xëtu.

MIGRATIONS V1.8 depuis V1.7 :
  - FIX BUG-I3 : thread_id fallback Gemini séparé (évite historique croisé)

MIGRATIONS V1.7 depuis V1.6 :
  - _is_retryable_error simplifié : fallback Gemini uniquement sur rate limit (429)
    → llama3-groq-70b-8192-tool-use-preview gère les tool calls nativement,
      plus besoin de catcher BadRequestError/tool_use_failed
  - Fallback Gemini échoué → message propre à l'usager (plus de crash silencieux)
"""
import logging
import time

from langgraph.prebuilt import create_react_agent
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage


from config.settings import (
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
)

from agent.soul import SETU_SOUL

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
    model=GROQ_MODEL,          # llama3-groq-70b-8192-tool-use-preview
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
    """Fallback Gemini uniquement sur rate limit Groq (429).
    Les tool call errors ne déclenchent plus le fallback —
    llama3-groq-70b-8192-tool-use-preview les gère nativement.
    """
    if "RateLimitError" in type(exc).__name__ or "429" in str(exc):
        return True
    cause = getattr(exc, "__cause__", None)
    if cause and _is_retryable_error(cause):
        return True
    return False


# Cache des agents avec checkpointer
_agents_with_checkpointer: dict = {}


# PERF-1 : limite l'historique à 8 messages — stable dans LangGraph 1.0+
def _trim_messages(state: dict) -> dict:
    """Garde les 8 derniers messages + le system prompt."""
    messages = state.get("messages", [])
    from langchain_core.messages import SystemMessage
    system = [m for m in messages if isinstance(m, SystemMessage)]
    others = [m for m in messages if not isinstance(m, SystemMessage)]
    trimmed = others[-8:] if len(others) > 8 else others
    return {**state, "messages": system + trimmed}


def _get_agent_with_checkpointer(checkpointer, name: str):
    """Retourne un agent avec checkpointer, mis en cache par nom."""
    if name not in _agents_with_checkpointer:
        llm = _llm_gemini if name in ("gemini", "gemini-fallback") else _llm_groq
        _agents_with_checkpointer[name] = create_react_agent(
            model=llm,
            tools=ALL_TOOLS,
            prompt=SETU_SOUL,
            checkpointer=checkpointer,
            state_modifier=_trim_messages,  # PERF-1 : LangGraph 1.0+
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
            f"  Cause : {type(e).__name__}: {e}\n"
            f"  → Ajoutez DB_PASSWORD dans Railway pour activer la persistance."
        )
        import asyncio
        try:
            asyncio.get_running_loop().call_later(60, _reset_checkpointer_flag)
        except RuntimeError:
            pass  # Pas de loop active — le flag restera False jusqu'au prochain appel
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
    - Si Groq est rate-limité (429) : fallback Gemini.
    - Si Gemini échoue aussi : message propre à l'usager, pas de crash.
    """
    global _fallback_count

    # ── Choix de l'agent ─────────────────────────────────
    agent_name = "gemini" if langue == "wolof" else "groq"
    logger.info(f"[xetu_run] langue={langue!r} | phone=…{phone[-4:]!r} | agent={agent_name}")

    config = {
        "configurable": {
            "phone": phone,
            "thread_id": phone,
        }
    }

    # ── PERF-3 : Intent cache — court-circuit pour patterns fréquents ──
    # Patterns simples (salutations, questions répétées) → pas d'appel LLM
    from agent import intent_cache as _ic
    from agent.normalizer import normalize_for_cache
    try:
        cached = _ic.get(normalize_for_cache(message))
        if cached:
            logger.info(f"[xetu_run] Cache HIT → {cached!r}")
            # Le cache retourne une réponse directe pour les patterns ultra-simples
            # Pour les intents complexes on laisse l'agent gérer
            if cached in ("greeting",):
                return "Salam ! Dis-moi pour quel bus tu as besoin. 🚌 — *Xëtu*"
    except Exception:
        pass  # Cache indisponible → continuer normalement

    # ── Tentative avec checkpointer ───────────────────────
    checkpointer = await _try_get_checkpointer()

    if checkpointer:
        agent = _get_agent_with_checkpointer(checkpointer, agent_name)
        try:
            return await _invoke_agent(agent, message, config)
        except Exception as e:
            if _is_retryable_error(e) and agent_name == "groq":
                _fallback_count += 1
                logger.warning(
                    f"[xetu_run] Groq rate-limité → fallback Gemini (#{_fallback_count}): "
                    f"{type(e).__name__}: {str(e)[:100]}"
                )
                try:
                    fallback = _get_agent_with_checkpointer(checkpointer, "gemini-fallback")
                    # FIX BUG-I3 : thread_id distinct pour éviter historique croisé groq/gemini
                    fb_config = {**config, "configurable": {**config["configurable"], "thread_id": f"{phone}_fb"}}
                    return await _invoke_agent(fallback, message, fb_config)
                except Exception as fb_err:
                    logger.error(f"[xetu_run] Fallback Gemini échoué: {fb_err}")
                    return "Le service est temporairement surchargé. Réessaie dans un moment. 🙏"
            raise

    # ── Mode SANS checkpointer ────────────────────────────
    logger.info(f"[xetu_run] Mode sans checkpointer — agent={agent_name}")

    agent_base = _agent_gemini_base if agent_name == "gemini" else _agent_groq_base

    try:
        return await _invoke_agent(agent_base, message, config)
    except Exception as e:
        if _is_retryable_error(e) and agent_name == "groq":
            _fallback_count += 1
            logger.warning(
                f"[xetu_run] Groq rate-limité (no-cp) → fallback Gemini (#{_fallback_count}): "
                f"{type(e).__name__}: {str(e)[:100]}"
            )
            try:
                return await _invoke_agent(_agent_gemini_base, message, config)
            except Exception as fb_err:
                logger.error(f"[xetu_run] Fallback Gemini échoué: {fb_err}")
                return "Le service est temporairement surchargé. Réessaie dans un moment. 🙏"
        raise


def _extract_response(result: dict) -> str:
    last_msg = result["messages"][-1]
    response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    if not response or not response.strip():
        logger.warning("[xetu_run] Réponse vide de l'agent !")
        response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"
    logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
    return response