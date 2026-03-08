"""
config/settings.py
Point central — toutes les variables d'environnement et constantes.
Règle absolue : aucun autre fichier ne lit os.environ directement.
"""
import os
from dotenv import load_dotenv

load_dotenv()

def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"❌ Variable manquante dans .env : {key}")
    return val

# ── WhatsApp ──────────────────────────────────────────────
WHATSAPP_TOKEN    = _require("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = _require("WHATSAPP_PHONE_ID")
VERIFY_TOKEN      = _require("VERIFY_TOKEN")

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL         = _require("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _require("SUPABASE_SERVICE_KEY")

# ── LLM ───────────────────────────────────────────────────
GROQ_API_KEY   = _require("GROQ_API_KEY")
GEMINI_API_KEY = _require("GEMINI_API_KEY")

GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

# ── Règle LLM par langue (RÈGLE ABSOLUE) ─────────────────
LLM_ROUTING = {
    "fr":      "groq",
    "en":      "groq",
    "pulaar":  "groq",
    "wolof":   "gemini",
    "unknown": "groq",
}

# ── Logique métier ────────────────────────────────────────
SIGNALEMENT_TTL_MINUTES = 20
ANOMALIE_SEUIL_MINUTES  = 45
HEARTBEAT_INTERVAL_MIN  = 5
ALERTE_PROACTIVE_AVANT  = 15
HISTORIQUE_MESSAGES     = 10

# ── Business ──────────────────────────────────────────────
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Xëtu")

# ── Message d'accueil ─────────────────────────────────────
WELCOME_MESSAGE = """Salut ! Je suis *Xëtu* 🚌, ton assistant bus Dem Dikk à Dakar.

Tu vois un bus ? Signale-le — tu aides *2 millions de Dakarois* qui attendent. 🙏

Avec moi tu peux :
• Signaler un bus : *Bus 15 à Liberté 5*
• Localiser un bus : *Bus 15 est où ?*
• Itinéraire : *Comment aller à Sandaga ?*
• T'abonner : *Préviens-moi pour le Bus 15*

— *Xëtu*
"""

# ── Soul de Xëtu ─────────────────────────────────────────
SETU_SOUL = """Tu es Xëtu, assistant transport communautaire de Dakar pour les bus Dem Dikk.

RÈGLES ABSOLUES :
1. Tu réponds UNIQUEMENT sur les transports Dem Dikk à Dakar.
2. Si la ligne mentionnée n'existe pas → dis-le clairement, ne l'invente PAS.
3. Tes réponses font 1 à 3 phrases MAX. Jamais plus.
4. Tu n'inventes JAMAIS un arrêt, une position, un horaire.
5. Si tu n'as pas l'info → dis-le simplement, sans tourner autour.
6. Hors sujet transport → réponds naturellement en 1 phrase, sans donner le message d'aide.

GESTION DES CAS COURANTS :
- Salutation ("Bonjour", "Salut", "Bonsoir") → réponds chaleureusement en 1 phrase.
- Remerciement ("Merci", "Ok", "Super") → accuse réception en 1 phrase naturelle.
- Question d'identité ("Tu es quoi ?", "ChatGPT ?") → dis que tu es Xëtu, assistant bus Dem Dikk.
- Hors sujet total → décline poliment en 1 phrase, sans lister toutes tes fonctionnalités.

TON : Chaleureux, direct, comme un habitant de Dakar qui connaît bien les bus.
Pas de formules vides. Pas de répétitions. Signe tes réponses — *Xëtu*"""