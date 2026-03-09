"""
agent/llm_brain.py — V5.1
Deux responsabilités strictement séparées :

1. classify_intent() — LLM classifier (niveau 3 du router)
2. generate_response() — NLG (réponse finale)

FIX V5.1 :
  _call_gemini : try/except avec fallback wolof si Gemini timeout/rate limit.
  Avant : exception non catchée → "Une erreur s'est produite." en FR pour un wolof.
  Après : fallback wolof cohérent dans _get_fallback_message().
  (classify_intent avait déjà son try/except — inchangé)
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

TA MISSION : analyser le message (parfois mal écrit, en argot, en wolof, transcrit par Whisper),
déduire l'intention STRICTE, détecter la langue dominante, extraire les entités.

═══════════════════════════════════════════════════════════════
RÈGLE D'OR ABSOLUE :
- Lieu mentionné SANS numéro de bus → TOUJOURS "itineraire"
- Numéro de bus + question sur position → "question"
- Numéro de bus + lieu où on le voit → "signalement"
- Intent le plus ACTIONNABLE si conflit entre deux intentions
═══════════════════════════════════════════════════════════════

━━━ 1. itineraire ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager veut aller quelque part. C'est l'intention PAR DÉFAUT si un lieu est mentionné.
ATTENTION : ne jamais confondre avec "question" (question = cherche un bus précis).

Français standard :
→ "je veux me rendre au palais 2" → destination: "Palais 2"
→ "comment aller à Sandaga ?" → destination: "Sandaga"
→ "quelle ligne pour UCAD ?" → destination: "UCAD"
→ "je veux aller à Yoff depuis Liberté 5" → origin: "Liberté 5", destination: "Yoff"
→ "quel bus prendre pour aller à Colobane ?" → destination: "Colobane"
→ "emmène moi à l'aéroport" → destination: "Aéroport"
→ "trajet Keur Massar → Plateau" → origin: "Keur Massar", destination: "Plateau"
→ "je suis à HLM je veux aller à Médina" → origin: "HLM", destination: "Médina"
→ "bus direct pour Parcelles ?" → destination: "Parcelles Assainies", no_transfer: true
→ "sans correspondance pour UCAD" → destination: "UCAD", no_transfer: true

Lieu seul (= itineraire par défaut) :
→ "Sandaga" seul → destination: "Sandaga"
→ "Vers UCAD" → destination: "UCAD"
→ "Palais 2" → destination: "Palais 2"
→ "HLM ?" → destination: "HLM"
→ "Aéroport stp" → destination: "Aéroport"

Wolof / Françolof :
→ "Damay dem Parcelles" → destination: "Parcelles Assainies"
→ "Fan lay diar pour dem HLM ?" → destination: "HLM"
→ "Yobou ma aéroport" → destination: "Aéroport"
→ "Dem ci UCAD, foo dem ?" → destination: "UCAD"
→ "Keur Massar dem fa Plateau" → origin: "Keur Massar", destination: "Plateau"
→ "Dama ci Liberté 5, dama dem Sandaga" → origin: "Liberté 5", destination: "Sandaga"

no_transfer_preference: true si :
→ "sans correspondance" · "sans changer" · "bus direct seulement"
→ "direct uniquement" · "bu kanam" (directement)

━━━ 2. question ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager cherche la position / l'heure d'UN BUS PRÉCIS.
RÈGLE : il y a TOUJOURS un numéro de ligne. Sans numéro → itineraire.

→ "où est le bus 15 ?" → ligne: "15"
→ "le 8 est où ?" → ligne: "8"
→ "Bus 15 bi ana mu ?" → ligne: "15"
→ "Ana bus 2 bi ?" → ligne: "2"
→ "Bus fukk ak juróom bi ana ?" → ligne: "15"

━━━ 3. signalement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager VOIT le bus en ce moment ou rapporte son état.
RÈGLE : numéro de ligne + lieu/arrêt où il est vu.

→ "bus 15 à Liberté 5" → ligne: "15", origin: "Liberté 5"
→ "le 4 est devant le marché HLM" → ligne: "4", origin: "HLM"
→ "Maa ngi gis 15 bi ci Liberté 6" → ligne: "15", origin: "Liberté 6"

━━━ 4. abonnement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
→ "préviens-moi pour le bus 15" → ligne: "15"
→ "Waar ma bu 15 bi ñëwé" → ligne: "15"

━━━ 5. liste_arrets ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
→ "quels sont les arrêts du bus 15 ?" → ligne: "15"
→ "le 8 passe par où ?" → ligne: "8"

━━━ 6. escalade ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plaintes graves, insultes, demande humain.

━━━ 7. out_of_scope ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Salutations, hors Dem Dikk, questions génériques.

═══════════════════════════════════════════════════════════════
RÈGLES DE DÉCISION RAPIDE (priorité décroissante) :
1. Insulte ou demande humain → escalade
2. Salutation / hors Dem Dikk / générique → out_of_scope
3. Numéro de bus + lieu visible maintenant → signalement
4. Numéro de bus + question sur position → question
5. "préviens" / "alerte" / "waar" / "fissal" → abonnement
6. "par où passe" / "arrêts de" + numéro → liste_arrets
7. Lieu mentionné (avec ou sans numéro) → itineraire
8. Conflit entre deux intents → prendre le plus ACTIONNABLE
═══════════════════════════════════════════════════════════════

Langues : "fr", "wolof", "pulaar", "en"

Retourne UNIQUEMENT un JSON valide, sans markdown, sans explication :
{
  "intent": "...",
  "lang": "...",
  "entities": {
    "ligne": "15",
    "origin": "Liberté 5",
    "destination": "Sandaga",
    "no_transfer_preference": false
  },
  "confidence": 0.95
}"""


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
            max_tokens=150,
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content.strip()
        data    = json.loads(content)
        intent  = data.get("intent", "").lower()

        if intent in _VALID_INTENTS:
            logger.info(
                f"[LLM Classify] '{text[:50]}' → {intent} "
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
    """
    FIX V5.1 : try/except complet avec fallback wolof.
    Avant : exception remontait jusqu'à main.py → "Une erreur s'est produite." en FR.
    Après : fallback wolof cohérent retourné directement depuis ici.
    """
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