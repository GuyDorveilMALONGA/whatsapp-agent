"""
agent/llm_brain.py — V6.0
Deux responsabilités strictement séparées :
1. classify_intent() — LLM classifier (niveau 3 du router)
2. generate_response() — NLG (réponse finale)

MIGRATIONS V6.0 depuis V5.5 :
  - FIX L2 : Timeout sur TOUS les appels LLM (Groq + Gemini)
  - FIX L3 : JSON parsing défensif (strip markdown, fallback)
  - FIX L4 : Historique 5 messages pour classifier (était 3)
  - FIX L7 : Gemini reçoit un system_instruction séparé
  - Métriques de logging améliorées (temps de réponse)
"""
import json
import logging
import asyncio
import time
import re
import google.generativeai as genai
from groq import AsyncGroq

from config.settings import (
    GROQ_API_KEY, GEMINI_API_KEY,
    GROQ_MODEL, GEMINI_MODEL,
    LLM_ROUTING, SETU_SOUL,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_groq_client = AsyncGroq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

_VALID_INTENTS = {
    "abandon",
    "signalement", "question", "abonnement",
    "escalade", "liste_arrets", "itineraire",
    "out_of_scope", "alternatives_itineraire",
}

# Prompt classifier inchangé (déjà solide)
_CLASSIFY_SYSTEM = """Tu es l'intelligence NLP centrale de Xëtu, l'assistant transport Dem Dikk de Dakar.

RÉSEAU DEM DIKK (SEULES CES LIGNES EXISTENT) :
Urbaines : 1, 4, 7, 8, 9, 10, 13, 18, 20, 23, 121, 319, TO1, 501, 502, 503, TAF TAF
Banlieue : 2, 5, 6, 11, 12, 15, 16A, 16B, 208, 213, 217, 218, 219, 220, 221, 227, 232, 233, 234, 311, 327, RUF-YENNE

ARRÊTS FRÉQUENTS (normalise les fautes d'orthographe vers ces noms) :
Liberté 1/2/3/4/5/6, HLM, Sandaga, UCAD, Colobane, Yoff, Parcelles Assainies,
Grand Yoff, Médina, Plateau, Pompiers, Gare Routière, Petersen, Tilène,
Terminus Leclerc, Rond Point Liberté, RP6, Castor, Ouakam, Almadies,
Pikine, Guédiawaye, Keur Massar, Thiaroye, Rufisque, Mbao,
Palais Justice, Palais 2, Hôpital, Aéroport, Cambérène, Niary Tally, Point E.

NORMALISATION ORTHOGRAPHE ARRÊTS :
"Liberter 5" → Liberté 5 · "parcel" → Parcelles Assainies · "grand yof" → Grand Yoff
"médine" → Médina · "camberen" → Cambérène · "ker massar" → Keur Massar
"guediawaye" → Guédiawaye · "thiaroy" → Thiaroye · "pikeen" → Pikine
"HLM 5" → arrêt HLM (pas ligne 5)
"Liberté 6" → arrêt Liberté 6 (pas ligne 6) · "Palais 2" → arrêt (pas ligne 2)
"Castor" → arrêt Castor (pas une ligne) · "Point E" → arrêt (pas une ligne)

NUMÉROS DE BUS EN WOLOF :
"fukk" → 10 · "juróom ñaar" → 7 · "fukk ak juróom" → 15
"ñenent" → 4 · "juróom" → 5 · "juróom benn" → 6
"ñaar" → 2 · "benn" → 1 · "fukk ak benn" → 11

CORRECTIONS AUDIO WHISPER :
"bus case" / "bus casse" → ligne: "15"
"bus set" / "bus cette" → ligne: "7"
"bus wit" / "bus ouitte" → ligne: "8"
"bus nef" / "bus neve" → ligne: "9"
"bus dis" / "bus dice" → ligne: "10"
"bus onze" → ligne: "11" · "bus douze" → ligne: "12"

TA MISSION : analyser le message ET l'historique pour déduire l'intention RÉELLE.

═══════════════════════════════════════════════════════════════
PROTOCOLE D'ANALYSE — CHAIN OF THOUGHT (OBLIGATOIRE)

ÉTAPE 1 — ÉTAT D'ESPRIT : Annulation, refus, changement d'avis ?
  Si OUI → intent = "abandon" immédiatement.

ÉTAPE 2 — ENTITÉS : Seulement si pas un refus.

ÉTAPE 3 — CLASSIFICATION : Intent le plus cohérent avec l'ACTION souhaitée.
═══════════════════════════════════════════════════════════════

━━━ INTENTS (classés par priorité) ━━━━━━━━━━━━━━━━━━━━━━━━━

1. abandon — refus/annulation (PRIORITÉ ABSOLUE)
2. alternatives_itineraire — autres options après un itinéraire
3. itineraire — se déplacer (origin → destination)
4. question — position/heure d'un bus précis
5. signalement — l'usager VOIT le bus (ligne + lieu)
6. abonnement — alerte bus
7. liste_arrets — arrêts d'une ligne
8. escalade — plainte, humain
9. out_of_scope — hors sujet

FORMAT JSON STRICT :
{
  "thought": "Réflexion courte",
  "intent": "...",
  "lang": "fr|wolof|en|pulaar",
  "entities": {"ligne": "15", "origin": "Liberté 5", "destination": "Sandaga"},
  "confidence": 0.95
}

Langues détectables : "fr", "wolof", "pulaar", "en"
"""


def _safe_parse_json(content: str) -> dict | None:
    """
    FIX L3 : Parse JSON de manière défensive.
    Gère : markdown backticks, texte autour, JSON mal formé.
    """
    # Étape 1 : strip markdown
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    # Étape 2 : essai direct
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Étape 3 : chercher le premier { ... } dans le texte
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


async def classify_intent(
    text: str,
    history: list[dict] | None = None
) -> dict | None:
    messages = [{"role": "system", "content": _CLASSIFY_SYSTEM}]

    if history:
        # FIX L4 : 5 messages au lieu de 3
        recent = history[-5:]
        ctx    = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        messages.append({
            "role": "user",
            "content": f"Historique:\n{ctx}\n\nMessage à classifier: {text}"
        })
    else:
        messages.append({"role": "user", "content": text})

    start_time = time.monotonic()

    try:
        # FIX L2 : timeout
        response = await asyncio.wait_for(
            _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                max_tokens=300,
                temperature=0.0,
                response_format={"type": "json_object"}
            ),
            timeout=LLM_TIMEOUT_SECONDS
        )
        elapsed = time.monotonic() - start_time
        content = response.choices[0].message.content.strip()

        # FIX L3 : parsing défensif
        data = _safe_parse_json(content)
        if not data:
            logger.warning(f"[LLM Classify] JSON invalide après {elapsed:.1f}s: {content[:100]}")
            return None

        intent = data.get("intent", "").lower()

        if intent in _VALID_INTENTS:
            logger.info(
                f"[LLM Classify] '{text[:50]}' → {intent} "
                f"| {elapsed:.1f}s "
                f"| thought={data.get('thought', '')[:80]} "
                f"| entities={data.get('entities')}"
            )
            return data

        logger.warning(f"[LLM Classify] Intent invalide: {intent} ({elapsed:.1f}s)")
        return None

    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start_time
        logger.error(f"[LLM Classify] TIMEOUT après {elapsed:.1f}s pour: {text[:50]}")
        return None
    except Exception as e:
        elapsed = time.monotonic() - start_time
        logger.error(f"[LLM Classify] Erreur après {elapsed:.1f}s: {e}")
        return None


async def generate_response(
    context: str,
    langue: str,
    history: list[dict] | None = None
) -> str:
    provider = "gemini" if langue == "wolof" else LLM_ROUTING.get(langue, "groq")
    prompt   = _build_prompt(context, langue, history or [])

    if provider == "gemini":
        return await _call_gemini(prompt, langue)
    else:
        return await _call_groq(prompt, langue)


def _build_prompt(context: str, langue: str, history: list[dict]) -> str:
    langue_label = {
        "fr":      "français",
        "en":      "anglais",
        "wolof":   "wolof urbain de Dakar (naturel, pas de traduction littérale)",
        "pulaar":  "pulaar",
        "unknown": "français",
    }.get(langue, "français")

    if langue == "wolof":
        langue_warning = (
            "\n⚠️ LANGUE STRICTE : wolof UNIQUEMENT. "
            "Zéro mot en français sauf noms propres d'arrêts."
        )
    elif langue == "fr":
        langue_warning = (
            "\n⚠️ LANGUE STRICTE : français UNIQUEMENT. "
            "Zéro mot en wolof, même en conclusion ou signature. "
            "Les exemples wolof du SOUL sont des références de style, "
            "PAS des phrases à reproduire pour un usager francophone."
        )
    elif langue == "en":
        langue_warning = (
            "\n⚠️ LANGUE STRICTE : anglais UNIQUEMENT. "
            "Zéro mot en wolof ou en français sauf noms propres d'arrêts."
        )
    else:
        langue_warning = ""

    history_text = ""
    if history:
        lines = [
            f"{'Usager' if m['role'] == 'user' else 'Xëtu'}: {m['content']}"
            for m in history[-6:]
        ]
        history_text = "\n".join(lines)

    return f"""{SETU_SOUL}

LANGUE DE RÉPONSE OBLIGATOIRE : {langue_label}{langue_warning}

{f"HISTORIQUE RÉCENT :{chr(10)}{history_text}{chr(10)}" if history_text else ""}SITUATION ACTUELLE :
{context}

Rédige la réponse finale. 1 à 3 phrases MAX. Naturel et direct."""


async def _call_groq(prompt: str, langue: str) -> str:
    start_time = time.monotonic()
    try:
        # FIX L2 : timeout
        response = await asyncio.wait_for(
            _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.4,
            ),
            timeout=LLM_TIMEOUT_SECONDS
        )
        elapsed = time.monotonic() - start_time
        logger.debug(f"[Groq] Réponse en {elapsed:.1f}s")
        return response.choices[0].message.content.strip()
    except asyncio.TimeoutError:
        logger.error(f"[Groq] TIMEOUT après {LLM_TIMEOUT_SECONDS}s")
        return _get_fallback_message(langue)
    except Exception as e:
        logger.error(f"[Groq] Erreur generate: {e}")
        return _get_fallback_message(langue)


async def _call_gemini(prompt: str, langue: str) -> str:
    start_time = time.monotonic()
    try:
        # FIX L7 : system_instruction séparé pour Gemini
        model = genai.GenerativeModel(
            GEMINI_MODEL,
            system_instruction=SETU_SOUL,
        )
        # FIX L2 : timeout
        response = await asyncio.wait_for(
            model.generate_content_async(prompt),
            timeout=LLM_TIMEOUT_SECONDS
        )
        elapsed = time.monotonic() - start_time
        text = response.text.strip()
        if not text:
            raise ValueError("Réponse Gemini vide")
        logger.debug(f"[Gemini] Réponse en {elapsed:.1f}s")
        return text
    except asyncio.TimeoutError:
        logger.error(f"[Gemini] TIMEOUT après {LLM_TIMEOUT_SECONDS}s")
        return _get_fallback_message(langue)
    except Exception as e:
        logger.error(f"[Gemini] Erreur generate: {e}")
        return _get_fallback_message(langue)


def _get_fallback_message(langue: str) -> str:
    fallbacks = {
        "wolof":  "Baal ma, am na luy xat-xat ci samay masin. Ma ngi ñëw ci kanam. 🙏",
        "en":     "Sorry, a technical error occurred. Please try again. 🙏",
        "pulaar": "Yonaande, goonga fewndo e ngañgu. Tiiɗno immin. 🙏",
        "fr":     "Désolé, une erreur s'est produite. Réessaie dans un instant. 🙏",
    }
    return fallbacks.get(langue, fallbacks["fr"])