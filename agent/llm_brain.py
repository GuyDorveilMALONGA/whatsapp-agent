"""
agent/llm_brain.py — V5.3
Deux responsabilités strictement séparées :

1. classify_intent() — LLM classifier (niveau 3 du router)
2. generate_response() — NLG (réponse finale)

FIX V5.3 :
  Chain of Thought (CoT) : champ "thought" ajouté au format de sortie.
  Le LLM est forcé de verbaliser l'état d'esprit de l'usager AVANT
  de classifier. Empêche la règle "lieu → itineraire" d'écraser
  les cas d'annulation/refus.

  Ex: "Oublie pour la ligne 8"
    thought: "L'usager cite la ligne 8 mais utilise 'oublie'. Annulation claire."
    intent: "abandon"

  Ex: "Je ne veux aller nulle part"
    thought: "Négation explicite + absence de destination réelle. Refus."
    intent: "abandon"
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

_groq_client = AsyncGroq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

_VALID_INTENTS = {
    "abandon",
    "signalement", "question", "abonnement",
    "escalade", "liste_arrets", "itineraire", "out_of_scope"
}

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
"plateau" reste plateau · "HLM 5" → arrêt HLM (pas ligne 5)
"Liberté 6" → arrêt Liberté 6 (pas ligne 6) · "Palais 2" → arrêt (pas ligne 2)
"Castor" → arrêt Castor (pas une ligne) · "Point E" → arrêt (pas une ligne)

NUMÉROS DE BUS EN WOLOF :
"fukk" → 10 · "juróom ñaar" → 7 · "fukk ak juróom" → 15
"ñenent" → 4 · "juróom" → 5 · "juróom benn" → 6
"ñaar" → 2 · "benn" → 1 · "fukk ak benn" → 11

CORRECTIONS AUDIO WHISPER (fautes phonétiques fréquentes) :
"bus case" / "bus casse" / "bus cannes" → ligne: "15"
"bus set" / "bus cette" / "bus sette" → ligne: "7"
"bus wit" / "bus ouitte" / "bus ouit" → ligne: "8"
"bus nef" / "bus neve" → ligne: "9"
"bus dis" / "bus dice" → ligne: "10"
"bus onze" → ligne: "11" · "bus douze" → ligne: "12"
"bus vingt trois" → ligne: "23" · "bus deuce" → ligne: "2"
"bus un" → ligne: "1" · "bus trente" → null (pas de ligne 30)

TA MISSION : analyser le message (parfois mal écrit, en argot, en wolof, transcrit par Whisper)
ET l'historique récent pour déduire l'intention RÉELLE de l'usager.

═══════════════════════════════════════════════════════════════
PROTOCOLE D'ANALYSE — CHAIN OF THOUGHT (OBLIGATOIRE)

Avant de classifier, tu DOIS analyser l'état d'esprit de l'usager dans le champ "thought".
Ce champ est ta réflexion interne. Suis ces étapes dans l'ordre :

ÉTAPE 1 — ÉTAT D'ESPRIT : L'usager exprime-t-il une annulation, un refus, un
  changement d'avis, une négation ? Mots-clés : "oublie", "laisse", "non",
  "nulle part", "rien", "basta", "wëcciku", "bayil", "forget it", "never mind".
  Si OUI → intent = "abandon" immédiatement, sans extraire d'entités.

ÉTAPE 2 — ENTITÉS : Seulement si l'état d'esprit n'est PAS un refus, extraire
  les entités pertinentes (ligne, origin, destination).

ÉTAPE 3 — CLASSIFICATION : Choisir l'intent le plus cohérent avec l'action
  souhaitée, pas avec les mots-clés présents.
═══════════════════════════════════════════════════════════════

━━━ 1. abandon (PRIORITÉ ABSOLUE) ━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager annule, refuse, exprime un changement d'avis.
⚠️ La présence d'un numéro de ligne ou d'un lieu NE CHANGE RIEN si le verbe exprime un refus.

Français :
→ "oublie" / "oublie pour la ligne 8" / "laisse tomber" / "annule"
→ "je ne veux aller nulle part" / "je veux rien" / "non merci" / "c'est bon"
→ "peu importe" / "pas la peine" / "oublie ça" / "non finalement"
→ "je m'en fous" / "tant pis" / "basta" / "stop"

Wolof :
→ "wëcciku" / "sëde ko" / "du dara" / "amul solo"
→ "bëgguma" / "duma ko bëgg" / "bayil lolu" / "bayil"

Anglais :
→ "forget it" / "never mind" / "cancel" / "no thanks" / "don't bother"

━━━ 2. itineraire ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager veut RÉELLEMENT se déplacer. Intent par défaut si un lieu est mentionné
ET qu'il n'y a aucun refus/négation.

→ "je veux aller à Yoff depuis Liberté 5" → origin: "Liberté 5", destination: "Yoff"
→ "comment aller à Sandaga ?" → destination: "Sandaga"
→ "quelle ligne pour UCAD ?" → destination: "UCAD"
→ "Sandaga" seul → destination: "Sandaga"
→ "Damay dem Parcelles" → destination: "Parcelles Assainies"
→ "sans correspondance pour UCAD" → destination: "UCAD", no_transfer_preference: true

━━━ 3. question ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager cherche la position/heure d'UN BUS PRÉCIS. Contient TOUJOURS un numéro.

→ "où est le bus 15 ?" → ligne: "15"
→ "le 8 est où ?" → ligne: "8"
→ "Bus 15 bi ana mu ?" → ligne: "15"

━━━ 4. signalement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager VOIT le bus maintenant. Numéro + lieu visible.

→ "bus 15 à Liberté 5" → ligne: "15", origin: "Liberté 5"
→ "le 4 est devant le marché HLM" → ligne: "4", origin: "HLM"

━━━ 5. abonnement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
→ "préviens-moi pour le bus 15" → ligne: "15"
→ "Waar ma bu 15 bi ñëwé" → ligne: "15"

━━━ 6. liste_arrets ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
→ "quels sont les arrêts du bus 15 ?" → ligne: "15"
→ "le 8 passe par où ?" → ligne: "8"

━━━ 7. escalade ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plaintes graves, insultes, demande d'un humain.

━━━ 8. out_of_scope ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Salutations, hors Dem Dikk, questions génériques sur Xëtu.

═══════════════════════════════════════════════════════════════
FORMAT DE SORTIE — JSON STRICT, AUCUN MARKDOWN

Le champ "thought" est OBLIGATOIRE. C'est ta réflexion avant de classifier.

Exemple — annulation avec numéro de ligne :
{
  "thought": "L'usager cite la ligne 8 mais utilise le verbe 'oublie'. La présence du numéro ne change rien : c'est une annulation explicite de l'action en cours.",
  "intent": "abandon",
  "lang": "fr",
  "entities": {},
  "confidence": 0.98
}

Exemple — négation de destination :
{
  "thought": "L'usager dit 'nulle part' avec une négation forte. Il ne demande pas d'itinéraire, il refuse d'en donner un. Abandon.",
  "intent": "abandon",
  "lang": "fr",
  "entities": {},
  "confidence": 0.97
}

Exemple — itinéraire normal :
{
  "thought": "L'usager donne un lieu de destination sans aucun signe de refus. Itinéraire classique.",
  "intent": "itineraire",
  "lang": "fr",
  "entities": {
    "destination": "Parcelles Assainies"
  },
  "confidence": 0.95
}

Exemple — signalement :
{
  "thought": "L'usager signale voir le bus 15 à un arrêt précis maintenant.",
  "intent": "signalement",
  "lang": "fr",
  "entities": {
    "ligne": "15",
    "origin": "Liberté 5"
  },
  "confidence": 0.96
}
═══════════════════════════════════════════════════════════════

Langues détectables : "fr", "wolof", "pulaar", "en"
"""


async def classify_intent(
    text: str,
    history: list[dict] | None = None
) -> dict | None:
    messages = [{"role": "system", "content": _CLASSIFY_SYSTEM}]

    if history:
        recent = history[-3:]
        ctx    = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
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
            max_tokens=250,   # augmenté pour le champ thought
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        data    = json.loads(content)
        intent  = data.get("intent", "").lower()

        if intent in _VALID_INTENTS:
            logger.info(
                f"[LLM Classify] '{text[:50]}' → {intent} "
                f"| thought={data.get('thought', '')[:80]} "
                f"| lang={data.get('lang')} "
                f"| entities={data.get('entities')} "
                f"| confidence={data.get('confidence', '?')}"
            )
            return data

        logger.warning(f"[LLM Classify] Intent invalide reçu: {intent}")
        return None

    except Exception as e:
        logger.error(f"[LLM Classify] Erreur: {e}")
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

    history_text = ""
    if history:
        lines = [
            f"{'Usager' if m['role'] == 'user' else 'Xëtu'}: {m['content']}"
            for m in history[-6:]
        ]
        history_text = "\n".join(lines)

    return f"""{SETU_SOUL}

LANGUE DE RÉPONSE OBLIGATOIRE : {langue_label}

{f"HISTORIQUE RÉCENT :{chr(10)}{history_text}{chr(10)}" if history_text else ""}SITUATION ACTUELLE :
{context}

Rédige la réponse finale. 1 à 3 phrases MAX. Naturel et direct."""


async def _call_groq(prompt: str, langue: str) -> str:
    try:
        response = await _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"[Groq] Erreur generate: {e}")
        return _get_fallback_message(langue)


async def _call_gemini(prompt: str, langue: str) -> str:
    try:
        model    = genai.GenerativeModel(GEMINI_MODEL)
        response = await model.generate_content_async(prompt)
        text     = response.text.strip()
        if not text:
            raise ValueError("Réponse Gemini vide")
        return text
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