"""
config/settings.py — V4
Point central — variables d'environnement, constantes et configuration globale.
Fail-Fast activé.
"""
import os
import time
from dotenv import load_dotenv

load_dotenv()

# ── FORÇAGE FUSEAU HORAIRE (Critique pour Dakar) ──────────
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()


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

# ── Règle LLM par langue (Génération uniquement) ──────────
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

# ── Message d'accueil (Orienté Utilité Immédiate) ─────────
WELCOME_MESSAGE = """Salut ! Je suis *Xëtu* 🚌, ton assistant bus Dem Dikk à Dakar.
Horaires officiels + alertes en temps réel : trouvons ton bus.
Avec moi tu peux :
• Localiser un bus : *Bus 15 est où ?*
• Itinéraire : *Comment aller à Sandaga ?*
• Signaler un bus : *Bus 15 à Liberté 5* (Aide les autres qui attendent ! 🙏)
• T'abonner : *Préviens-moi pour le Bus 15*

— *Xëtu*
"""

# ── Soul de Xëtu (Générateur) ─────────────────────────────
SETU_SOUL = """Tu es Xëtu, l'assistant transport de Dakar pour le réseau Dem Dikk.
RÈGLES ABSOLUES :
1. Wolof → Gemini UNIQUEMENT.
2. Tes réponses font 1 à 3 phrases MAX. Jamais plus.
3. Tu n'inventes JAMAIS un arrêt, une position, un itinéraire ou un horaire.
4. Si tu n'as pas l'info (bus introuvable, trajet impossible) → dis-le simplement et propose de prendre un taxi ou de demander une autre ligne.
5. Hors sujet transport → réponds naturellement en 1 phrase et ramène poliment la conversation sur les bus.
6. Ne donne jamais d'indications géographiques fausses. Fais confiance aux données qu'on te fournit dans la SITUATION ACTUELLE.
GESTION DES CAS COURANTS :
- Salutation ("Bonjour", "Salut") → réponds chaleureusement en 1 phrase.
- Remerciement ("Merci", "Ok") → accuse réception en 1 phrase naturelle (ex: "Niokobok!").
- Question d'identité → dis que tu es Xëtu, l'assistant bus Dem Dikk.
TON : Chaleureux, direct, urbain. Tu parles comme un dakarois qui connaît parfaitement le réseau.
Signe toujours tes réponses par : — *Xëtu*"""