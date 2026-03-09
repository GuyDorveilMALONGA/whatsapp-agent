"""
agent/llm_brain.py — V5.0
Deux responsabilités strictement séparées :

1. classify_intent() — LLM classifier (niveau 3 du router)
   Input  : message normalisé + historique
   Output : dict complet {intent, lang, entities, confidence}
   Modèle : Groq Llama 3.3 70B (rapide, < 400ms, temperature=0)

2. generate_response() — NLG (réponse finale)
   Input  : contexte complet préparé par context_builder
   Output : réponse naturelle dans la bonne langue
   Modèle : Groq (fr/en/pul) ou Gemini (wo)

RÈGLE ABSOLUE : Wolof → Gemini UNIQUEMENT. Jamais Groq pour le wolof.

V5.0 :
  + classify_intent retourne dict complet (pas juste string)
  + generate_content_async (Gemini non-bloquant)
  + _get_fallback_message par langue (pas de fallback FR pour wolof)
  + Prompt TITANIUM V2 avec argot dakarois, Whisper, wolof exhaustif
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

# ── Init clients ──────────────────────────────────────────
_groq_client = AsyncGroq(api_key=GROQ_API_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# ── Intents valides ───────────────────────────────────────
_VALID_INTENTS = {
    "signalement", "question", "abonnement",
    "escalade", "liste_arrets", "itineraire", "out_of_scope"
}

# ── Prompt TITANIUM V2 ────────────────────────────────────
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
→ "je prends le 15 ou le 8 pour aller à Yoff ?" → destination: "Yoff" (choix = itineraire)
→ "sans correspondance pour UCAD" → destination: "UCAD", no_transfer: true
→ "itinéraire Pikine Sandaga" → origin: "Pikine", destination: "Sandaga"

Lieu seul (= itineraire par défaut) :
→ "Sandaga" seul → destination: "Sandaga"
→ "Vers UCAD" → destination: "UCAD"
→ "Palais 2" → destination: "Palais 2"
→ "HLM ?" → destination: "HLM"
→ "Aéroport stp" → destination: "Aéroport"

Cas ambigus résolus :
→ "je veux aller à Sandaga, le 8 passe par là ?" → itineraire (destination: "Sandaga")
→ "15 ou 8 pour Yoff ?" → itineraire (destination: "Yoff")
→ "j'attends le bus pour UCAD" → itineraire (destination: "UCAD")

Wolof / Françolof :
→ "Damay dem Parcelles" → destination: "Parcelles Assainies"
→ "Fan lay diar pour dem HLM ?" → destination: "HLM"
→ "Yobou ma aéroport" → destination: "Aéroport"
→ "Dama yakk bëgg dem vite fait Sandaga" → destination: "Sandaga"
→ "Dem ci UCAD, foo dem ?" → destination: "UCAD"
→ "Def naa dem Médina, lan laa jël ?" → destination: "Médina"
→ "Dem fa Colobane bu kanam" → destination: "Colobane", no_transfer: true
→ "Xam nga bus bi dem UCAD ?" → destination: "UCAD"
→ "Bëgg naa dem Gare, lan laa jël ?" → destination: "Gare Routière"
→ "Keur Massar dem fa Plateau" → origin: "Keur Massar", destination: "Plateau"
→ "Dama ci Liberté 5, dama dem Sandaga" → origin: "Liberté 5", destination: "Sandaga"

no_transfer_preference: true si :
→ "sans correspondance" · "sans changer" · "bus direct seulement"
→ "je ne peux pas marcher" · "direct uniquement" · "bu kanam" (directement)
→ "direct seulement" · "sans escale"

━━━ 2. question ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager cherche la position / l'heure d'UN BUS PRÉCIS.
RÈGLE : il y a TOUJOURS un numéro de ligne. Sans numéro → itineraire.

Cas "j'attends" avec numéro = question :
→ "j'attends le 15 depuis 30 min" → question, ligne: "15"
→ "je suis à l'arrêt du 8" → question, ligne: "8"
→ "le bus tarde" SANS numéro → itineraire (pas question)
→ "ça fait 1h que j'attends" SANS numéro → itineraire

Français standard :
→ "où est le bus 15 ?" → ligne: "15"
→ "le 8 est où ?" → ligne: "8"
→ "bus 15 est à combien d'arrêts ?" → ligne: "15"
→ "à quelle heure arrive le 121 ?" → ligne: "121"
→ "le 4 est loin ?" → ligne: "4"
→ "bus 6 est passé ?" → ligne: "6"
→ "depuis combien de temps le 15 est signalé ?" → ligne: "15"

Wolof / Françolof :
→ "Bus 15 bi ana mu ?" → ligne: "15"
→ "Ndax 121 bi romb na fi ?" → ligne: "121"
→ "Dama tardé, bus 8 bi ñëwul" → ligne: "8"
→ "Kañ lay nieuw 15 bi ?" → ligne: "15"
→ "Ana bus 2 bi ?" → ligne: "2"
→ "15 bi jappoo na ?" → ligne: "15"
→ "Bus 23 bi dafa yëngu ?" → ligne: "23"
→ "Bus fukk ak juróom bi ana ?" → ligne: "15"

━━━ 3. signalement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager VOIT le bus en ce moment ou rapporte son état.
RÈGLE : numéro de ligne + lieu/arrêt où il est vu.

Signalement passif (usager dans le bus) :
→ "je suis dans le 15" → signalement, ligne: "15" (origin = arrêt actuel si précisé)
→ "on est au niveau de Sandaga dans le 8" → signalement, ligne: "8", origin: "Sandaga"
→ "maa ngi ci bus 15 ci Colobane" → signalement, ligne: "15", origin: "Colobane"

Français standard :
→ "bus 15 à Liberté 5" → ligne: "15", origin: "Liberté 5"
→ "le 4 est devant le marché HLM" → ligne: "4", origin: "HLM"
→ "je vois le 8 près de Sandaga" → ligne: "8", origin: "Sandaga"
→ "accident bus 8 sur la VDN" → ligne: "8", origin: "VDN"
→ "le 15 est coincé dans les embouteillages à Colobane" → ligne: "15", origin: "Colobane"
→ "bus 23 en panne à Colobane" → ligne: "23", origin: "Colobane"

Wolof / Françolof :
→ "Maa ngi gis 15 bi ci Liberté 6" → ligne: "15", origin: "Liberté 6"
→ "23 bi dafa fess dell ci HLM" → ligne: "23", origin: "HLM"
→ "Bus bi gassi na ci Sandaga" → origin: "Sandaga" (ligne null si pas précisée)
→ "15 bi romb na ma fi ndana ci Colobane" → ligne: "15", origin: "Colobane"
→ "8 bi nekk na ci rond point Liberté" → ligne: "8", origin: "Rond Point Liberté"
→ "Gis naa 4 bi ci Petersen" → ligne: "4", origin: "Petersen"

━━━ 4. abonnement ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager veut être notifié/alerté pour une ligne.

Français standard :
→ "préviens-moi pour le bus 15" → ligne: "15"
→ "alerte-moi quand le 8 arrive" → ligne: "8"
→ "je veux être notifié pour la ligne 6" → ligne: "6"
→ "surveille le 15 pour moi" → ligne: "15"
→ "avertis moi si le 8 passe" → ligne: "8"
→ "bip moi pour le 4" → ligne: "4"
→ "abonne-moi au bus 15" → ligne: "15"

Wolof / Françolof :
→ "Waar ma bu 15 bi ñëwé" → ligne: "15"
→ "Na ma message bi ñëwé bus 8" → ligne: "8"
→ "Sonal ma bu rombé 15 bi" → ligne: "15"
→ "Fissal ma pour bus 6" → ligne: "6"
→ "Wéer ma bi 121 bi ñëw" → ligne: "121"

━━━ 5. liste_arrets ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
L'usager veut savoir par où passe une ligne (pas un itineraire).

→ "quels sont les arrêts du bus 15 ?" → ligne: "15"
→ "le 8 passe par où ?" → ligne: "8"
→ "itinéraire de la ligne 6" → ligne: "6"
→ "liste des arrêts du 23" → ligne: "23"
→ "trajet complet bus 15" → ligne: "15"
→ "15 bi fumu diar ?" → ligne: "15"
→ "Yoonu bus 23 bi" → ligne: "23"
→ "Bus 8 bi diar foofeel ?" → ligne: "8"

━━━ 6. escalade ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plaintes graves, insultes, demande humain. Tolérance ZÉRO insultes.

Demande humain :
→ "je veux parler à un humain" · "passe moi le service client"
→ "votre bot est nul" · "ça ne marche pas du tout"
→ "j'ai un problème grave" · "je veux porter plainte"

Insultes / Trolls → escalade IMMÉDIATE :
→ "sa baye" / "sa yaye" · "bot bi dafa dof"
→ "dangeen di naxate" · "merde" · "ferme ta gueule"
→ "nul" / "idiot" · "lekk ma" · "dafa naxat"
→ toute insulte directe au bot ou à l'équipe

━━━ 7. out_of_scope ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Salutations, hors Dem Dikk, questions génériques.

Salutations (chaleureux, pas escalade) :
→ "bonjour" / "bonsoir" / "salut" · "nanga def" / "mbaa mu ngi"
→ "merci" / "jërëjëf" · "ok" / "d'accord" / "super" / "waaw"
→ "jai rom" (j'ai compris) · "waaw waaw"

Hors réseau Dem Dikk :
→ "Tata ligne 44" / "car rapide" / "ndiaga ndiaye"
→ "prix du TER" / "train express" · "taxi" / "Yango" / "moto"

Questions génériques :
→ "c'est combien le ticket ?" · "abonnement mensuel Dem Dikk ?"
→ "numéro de téléphone Dem Dikk" · "horaires du dimanche" sans ligne

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


# ── 1. CLASSIFY ───────────────────────────────────────────

async def classify_intent(
    text: str,
    history: list[dict] | None = None
) -> dict | None:
    """
    Niveau 3 du router — retourne dict complet ou None si échec.
    {intent, lang, entities: {ligne, origin, destination, no_transfer_preference}, confidence}
    Toujours Groq, temperature=0, response_format JSON.
    """
    messages = [{"role": "system", "content": _CLASSIFY_SYSTEM}]

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


# ── 2. GENERATE ───────────────────────────────────────────

async def generate_response(
    context: str,
    langue: str,
    history: list[dict] | None = None
) -> str:
    """
    Génère la réponse finale dans la bonne langue.
    Wolof → Gemini UNIQUEMENT. Jamais Groq pour le wolof.
    """
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
        lines = []
        for msg in history[-6:]:
            role = "Usager" if msg["role"] == "user" else "Xëtu"
            lines.append(f"{role}: {msg['content']}")
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
        # CRITIQUE : async pour ne pas bloquer l'event loop FastAPI
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"[Gemini] Erreur generate: {e}")
        return _get_fallback_message(langue)


def _get_fallback_message(langue: str) -> str:
    """Fallback cohérent par langue — pas de français pour le wolof."""
    fallbacks = {
        "wolof":  "Baal ma, am na luy xat-xat ci samay masin. Ma ngi ñëw ci kanam. 🙏",
        "en":     "Sorry, a technical error occurred. Please try again. 🙏",
        "pulaar": "Yonaande, goonga fewndo e ngañgu. Tiiɗno immin. 🙏",
        "fr":     "Désolé, une erreur s'est produite. Réessaie dans un instant. 🙏",
    }
    return fallbacks.get(langue, fallbacks["fr"])