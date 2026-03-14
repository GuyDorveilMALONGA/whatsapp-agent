"""
agent/xetu_agent.py — V1.3 (clean + fallback)
Agent ReAct LangGraph — cœur de Xëtu.

LLM routing :
  - Wolof  → Gemini 2.0 Flash
  - Autres → Llama 3.3 70B via Groq
  - Fallback : si Groq 429 → retry automatique avec Gemini

MIGRATIONS V1.3 depuis V1.2 :
  - Retrait des print() et traceback de debug
  - Fallback automatique Groq → Gemini sur RateLimitError
  - Compteur de fallbacks pour monitoring
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

# ── Compteur fallback pour monitoring ─────────────────────
_fallback_count = 0
_fallback_last_reset = time.time()


def get_fallback_stats() -> dict:
    """Stats de fallback — exposable via /health."""
    return {
        "fallback_count": _fallback_count,
        "since": _fallback_last_reset,
    }


# ── LLM Groq — Llama 3.3 70B (FR, EN, Pulaar, unknown) ──
_llm_groq = ChatGroq(
    model=GROQ_MODEL,
    temperature=0,
    api_key=GROQ_API_KEY,
    max_tokens=1024,
)

# ── LLM Gemini — pour le Wolof + fallback ─────────────────
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
    """
    if not history:
        return []

    messages = []
    for msg in history:
        role = msg.get("role", "").lower().strip()
        content = msg.get("content", "")

        if not content or not isinstance(content, str):
            continue

        content = content.strip()
        if not content:
            continue

        if role in ("user", "human"):
            messages.append(HumanMessage(content=content))
        elif role in ("assistant", "ai", "bot"):
            messages.append(AIMessage(content=content))

    return messages


# ══════════════════════════════════════════════════════════
# Détection RateLimitError (Groq 429)
# ══════════════════════════════════════════════════════════

def _is_rate_limit_error(exc: Exception) -> bool:
    """Détecte si l'exception est un rate limit Groq (429)."""
    exc_type = type(exc).__name__

    # Groq SDK lance groq.RateLimitError
    if "RateLimitError" in exc_type:
        return True

    # Parfois wrappé dans une autre exception
    if "429" in str(exc):
        return True

    # Vérifier la cause chaînée
    cause = getattr(exc, "__cause__", None)
    if cause and "RateLimitError" in type(cause).__name__:
        return True

    return False


# ══════════════════════════════════════════════════════════
# Point d'entrée unique
# ══════════════════════════════════════════════════════════

async def run(message: str, phone: str, langue: str = "fr", history: list = None) -> str:
    """
    Point d'entrée unique de Xëtu.

    Routing :
      - Wolof → Gemini directement
      - Autres → Groq, avec fallback Gemini si rate limit (429)
    """
    global _fallback_count

    # ── Conversion history → LangChain messages ──────────
    messages = _convert_history(history)
    messages.append(HumanMessage(content=message))

    # ── Choix de l'agent ─────────────────────────────────
    if langue == "wolof":
        agent = _agent_gemini
        agent_name = "gemini"
    else:
        agent = _agent_groq
        agent_name = "groq"

    logger.info(
        f"[xetu_run] langue={langue!r} | messages={len(messages)} "
        f"| phone={phone[:8]}… | agent={agent_name}"
    )

    config = {"configurable": {"phone": phone}}

    # ── Appel agent principal ────────────────────────────
    try:
        result = await agent.ainvoke({"messages": messages}, config=config)
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
                result = await _agent_gemini.ainvoke(
                    {"messages": messages}, config=config
                )
                return _extract_response(result)

            except Exception as fallback_err:
                logger.error(
                    f"[xetu_run] Fallback Gemini AUSSI en échec — "
                    f"{type(fallback_err).__name__}: {fallback_err}",
                    exc_info=True,
                )
                raise fallback_err

        # ── Autre erreur (pas un rate limit) ─────────────
        logger.error(
            f"[xetu_run] CRASH — {type(e).__name__}: {e}",
            exc_info=True,
        )
        raise


def _extract_response(result: dict) -> str:
    """Extrait la réponse texte du résultat LangGraph."""
    last_msg = result["messages"][-1]
    response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    if not response or not response.strip():
        logger.warning("[xetu_run] Réponse vide de l'agent !")
        response = "Désolé, je n'ai pas compris. Reformule ta demande. 🙏"

    logger.info(f"[xetu_run] réponse OK — {len(response)} chars")
    return response