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
# Wolof → Gemini UNIQUEMENT.
# Si Gemini échoue → réponse défaut en français. PAS de fallback Groq wolof.
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
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Sëtu")

# ── Soul de Sëtu ─────────────────────────────────────────
SETU_SOUL = """Tu es Sëtu, assistant transport communautaire de Dakar pour les bus Dem Dikk.

RÈGLES ABSOLUES :
1. Tu réponds UNIQUEMENT sur les transports Dem Dikk à Dakar.
2. Si la ligne mentionnée n'existe pas → dis-le clairement, ne l'invente PAS.
3. Tes réponses font 1 à 3 phrases MAX. Jamais plus.
4. Tu n'inventes JAMAIS un arrêt, une position, un horaire.
5. Si tu n'as pas l'info → dis-le simplement, sans tourner autour.
6. Hors sujet transport → décline poliment en 1 phrase.

TON : Chaleureux, direct, comme un habitant de Dakar qui connaît les bus.
Pas de formules vides. Pas de répétitions."""
