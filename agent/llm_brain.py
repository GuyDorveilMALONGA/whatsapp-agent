"""
agent/llm_brain.py
Deux responsabilités strictement séparées :

1. classify_intent() — LLM classifier (niveau 3 du router)
   Input  : message normalisé + historique
   Output : intent string uniquement (JSON structuré)
   Modèle : Groq Llama 3.3 70B (rapide, < 400ms, temperature=0)

2. generate_response() — NLG (réponse finale)
   Input  : contexte complet préparé par context_builder
   Output : réponse naturelle dans la bonne langue
   Modèle : Groq (fr/en/pul) ou Gemini (wo)

RÈGLE ABSOLUE : Wolof → Gemini UNIQUEMENT. Jamais Groq pour le wolof.
"""
import json
import logging
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

# ── Intents valides ───────────────────────────────────────
_VALID_INTENTS = {
    "signalement", "question", "abonnement",
    "escalade", "liste_arrets", "itineraire", "out_of_scope"
}

# ── Prompt classify ───────────────────────────────────────
# Lignes source : dem_dikk_lines.json (site officiel Dem Dikk · 39 lignes)
_CLASSIFY_SYSTEM = """Tu es un classificateur d'intentions pour Sëtu, assistant transport à Dakar.
Réseau Dem Dikk — lignes urbaines : 1, 4, 7, 8, 9, 10, 13, 18, 20, 23, 121, 319, TO1, 501, 502, 503, TAF TAF.
Lignes banlieue : 2, 5, 6, 11, 12, 15, 16A, 16B, 208, 213, 217, 218, 219, 220, 221, 227, 232, 233, 234, 311, 327, RUF-YENNE.

Intentions possibles :
- signalement  : l'usager signale la position d'un bus ("Bus 15 à Liberté 5", "le 8 est devant HLM")
- question     : l'usager demande où est un bus ou quand il arrive ("où est le 15 ?", "le bus est passé ?")
- abonnement   : l'usager veut être alerté pour une ligne ("préviens-moi pour le 15", "waar ma bus bi")
- liste_arrets : l'usager veut les arrêts d'une ligne ("arrêts du 15", "par où passe le 8 ?")
- itineraire   : l'usager veut savoir comment aller d'un endroit à un autre ("comment aller à Palais depuis Ouakam", "quel bus pour UCAD", "je suis à Yoff je vais à Sandaga")
- escalade     : l'usager veut un humain ou signale un problème grave
- out_of_scope : tout autre message (salutations, hors transport)

Retourne UNIQUEMENT un JSON valide, rien d'autre, pas de markdown :
{"intent": "...", "confidence": 0.95}"""


# ── 1. CLASSIFY ───────────────────────────────────────────

async def classify_intent(
    text: str,
    history: list[dict] | None = None
) -> str | None:
    """
    Niveau 3 du router — classification LLM uniquement.
    Retourne l'intent string ou None si échec.
    Toujours Groq (rapide, déterministe, temperature=0).
    """
    messages = [{"role": "system", "content": _CLASSIFY_SYSTEM}]

    # Contexte conversationnel — aide pour "et le 16 ?" ou messages wolof ambigus
    if history:
        recent = history[-3:]
        ctx = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
        messages.append({
            "role": "user",
            "content": f"Historique:\n{ctx}\n\nMessage à classifier: {text}"
        })
    else:
        messages.append({"role": "user", "content": text})

    try:
        response = await _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=50,
            temperature=0.0,  # déterministe — pas de créativité ici
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        data    = json.loads(content)
        intent  = data.get("intent", "").lower()

        if intent in _VALID_INTENTS:
            logger.info(
                f"[LLM Classify] '{text[:40]}' → {intent} "
                f"(confidence={data.get('confidence', '?')})"
            )
            return intent

        logger.warning(f"[LLM Classify] Intent invalide reçu: {intent}")
        return None

    except Exception as e:
        logger.error(f"[LLM Classify] Erreur: {e}")
        return None


# ── 2. GENERATE ───────────────────────────────────────────

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
    prompt   = _build_prompt(context, langue, history or [])

    if provider == "gemini":
        return await _call_gemini(prompt)
    else:
        return await _call_groq(prompt)


def _build_prompt(context: str, langue: str, history: list[dict]) -> str:
    langue_label = {
        "fr":      "français",
        "en":      "anglais",
        "wolof":   "wolof (langue naturelle, pas de traduction littérale du français)",
        "pulaar":  "pulaar",
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
        model    = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini error: {e}")
        # Fallback français — PAS de fallback Groq wolof
        return "Désolé, service temporairement indisponible. Réessaie dans un moment."