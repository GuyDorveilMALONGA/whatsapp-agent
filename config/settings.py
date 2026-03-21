"""
config/settings.py — V8.2
Point central — variables d'environnement, constantes, configuration globale.

MIGRATIONS V8.2 depuis V8.1 :
  - JSON_PATH : pointe vers routes_geometry_v13_fixed2.json
    (98 corrections interpolation + coupes boucles OSRM sur lignes 23/121/217/218/220)
  - EXCLUDED_LINES : set des lignes fantômes (1 arrêt, données incomplètes)
    exclues de VALID_LINES et du routage agent. Non supprimées du JSON.
  - VALID_LINES -= EXCLUDED_LINES appliqué après chargement dynamique.

MIGRATIONS V8.1 depuis V8.0 :
  - JSON_PATH : chemin absolu via pathlib.Path(__file__) pour Railway
    Le CWD sur Railway n'est pas garanti — __file__ l'est toujours.
    Plus de FileNotFoundError silencieux au cold start.

MIGRATIONS V8.0 depuis V7.0 :
  - VALID_LINES : généré dynamiquement depuis routes_geometry_v13.json
    Plus jamais de désynchronisation entre le JSON et le set hardcodé.
    Fallback sur le set V7 si le JSON est absent au démarrage.
  - JSON_PATH : constante centralisée pour le chemin du fichier de données
"""
import os
import re
import time
import json
import logging
import pathlib
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Validation phone E.164
PHONE_REGEX = re.compile(r'^[1-9]\d{6,14}$')

# Rate limiting
RATE_LIMIT_PER_PHONE_PER_MIN = 10
RATE_LIMIT_GLOBAL_PER_MIN    = 200

# ── FORÇAGE FUSEAU HORAIRE ────────────────────────────────
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"❌ Variable manquante dans .env : {key}")
    return val


# ── WhatsApp ──────────────────────────────────────────────
WHATSAPP_TOKEN      = _require("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID   = _require("WHATSAPP_PHONE_ID")
VERIFY_TOKEN        = _require("VERIFY_TOKEN")
WHATSAPP_APP_SECRET = _require("WHATSAPP_APP_SECRET")

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL         = _require("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _require("SUPABASE_SERVICE_KEY")
DATABASE_URL         = os.getenv("DATABASE_URL", "")  # optionnel désormais

# ── LLM ───────────────────────────────────────────────────
GROQ_API_KEY   = _require("GROQ_API_KEY")
GEMINI_API_KEY = _require("GEMINI_API_KEY")

GROQ_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL = "gemini-2.0-flash"

LLM_TIMEOUT_SECONDS = 15

# ── SaaS multi-tenant ─────────────────────────────────────
TENANT_ID = os.getenv("TENANT_ID", "dem-dikk-dakar")

# ── Routing LLM par langue ────────────────────────────────
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

# ── Sécurité ──────────────────────────────────────────────
# (RATE_LIMIT_PER_PHONE_PER_MIN défini une seule fois en haut)

# ── Business ──────────────────────────────────────────────
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Xëtu")

# ── Chemin JSON réseau ────────────────────────────────────
# V8.2 : pointe vers routes_geometry_v13_fixed2.json
# V8.1 : chemin absolu depuis la racine du projet via __file__
# config/settings.py → parent = config/ → parent = racine/
_BASE_DIR = pathlib.Path(__file__).parent.parent.resolve()
JSON_PATH = os.getenv(
    "NETWORK_JSON_PATH",
    str(_BASE_DIR / "routes_geometry_v13_fixed2.json")
)

logger.info(f"[Settings] JSON_PATH résolu → {JSON_PATH}")
logger.info(f"[Settings] Fichier existe  → {pathlib.Path(JSON_PATH).exists()}")


# ══════════════════════════════════════════════════════════
# SOURCE UNIQUE DE VÉRITÉ — LIGNES DEM DIKK
# V8.0 : généré dynamiquement depuis le JSON au démarrage.
# Tous les modules importent depuis ici — jamais de set dupliqué.
# ══════════════════════════════════════════════════════════

# Fallback V7 au cas où le JSON est absent (Railway cold start sans fichier)
_VALID_LINES_FALLBACK: set[str] = {
    "1", "2", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "15",
    "16A", "16B", "18", "20", "23", "121",
    "208", "213", "217", "218", "219", "220", "221", "227",
    "232", "233", "234", "311", "319", "327",
    "TO1", "501", "502", "503", "TAF TAF", "RUF-YENNE",
}


def _load_valid_lines(path: str) -> set[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lines = {str(k).upper() for k in (data.get("routes") or data.get("lignes", {})).keys()}
        if not lines:
            raise ValueError("routes vide")
        logger.info(f"[Settings] ✅ VALID_LINES chargé depuis {path} — {len(lines)} lignes")
        return lines
    except FileNotFoundError:
        logger.warning(f"[Settings] ⚠️ {path} introuvable — fallback V7 ({len(_VALID_LINES_FALLBACK)} lignes)")
        return _VALID_LINES_FALLBACK
    except Exception as e:
        logger.error(f"[Settings] ❌ Erreur chargement VALID_LINES : {e} — fallback V7")
        return _VALID_LINES_FALLBACK


VALID_LINES: set[str] = _load_valid_lines(JSON_PATH)

# ── V8.2 : Lignes exclues du routage ─────────────────────
# Lignes fantômes : 1 seul arrêt, données OSRM incomplètes,
# ou tronçons non opérationnels sur le réseau Dakar.
# Conservées dans le JSON pour traçabilité — ignorées par l'agent.
# Clés en majuscules pour correspondre au str(k).upper() du chargement.
EXCLUDED_LINES: set[str] = {
    "DDD_101",  # 504A       — 1 arrêt
    "DDD_103",  # HADARA     — 1 arrêt
    "DDD_104",  # TAF TAF JAXAAY — 1 arrêt
    "DDD_48",   # EXPRESS    — 1 arrêt
    "DDD_55",   # ISEP       — 1 arrêt
    "DDD_57",   # 504        — 1 arrêt
    "DDD_67",   # R02        — 2 arrêts, 1m36s (navette incomplète)
    "DDD_70",   # R08A       — 1 arrêt
    "DDD_71",   # R08B       — 1 arrêt
    "DDD_89",   # Y.NDI-OUR  — 1 arrêt (hors réseau Dakar)
    "DDD_90",   # Y.NDI-POD  — 1 arrêt (hors réseau Dakar)
    "DDD_92",   # L.S KED-SAL — 1 arrêt (hors réseau Dakar)
    "DDD_94",   # L.S KED-SAR — 1 arrêt (hors réseau Dakar)
    "DDD_98",   # 234 EXPRESS — 1 arrêt
}

VALID_LINES -= EXCLUDED_LINES
logger.info(
    f"[Settings] Lignes exclues : {len(EXCLUDED_LINES)} — "
    f"VALID_LINES final : {len(VALID_LINES)}"
)

# ── Message d'accueil ─────────────────────────────────────

WELCOME_MESSAGE = """Salut ! Je suis *Xëtu* 🚌, ton assistant bus Dem Dikk à Dakar.

Avec moi tu peux :
• Localiser un bus : *Bus 15 est où ?*
• Itinéraire : *Comment aller à Sandaga ?*
• Signaler un bus : *Bus 15 à Liberté 5* (Aide les autres ! 🙏)
• T'abonner : *Préviens-moi pour le Bus 15*

— *Xëtu*"""


# ══════════════════════════════════════════════════════════
# SETU_SOUL V8.0
# Fusion V7.0 (settings.py) + architecture cognitive V2 (doc interne)
# Ajouts V8.0 :
#   - [SYSTEM_INIT] / [END_SYSTEM_INIT] pour signaler les limites au LLM
#   - Protocoles A/B/C/D/E/F explicites (nouveaux : E=banlieue, F=multi-ligne)
#   - Dictionnaire wolof enrichi (bus express, terminus banlieue)
#   - Cas edge v13 : TAF TAF, lignes 200/300, RUF-YENNE
#   - Règle anti-ambiguïté 16A/16B
#   - Tous les exemples few-shot conservés + 8 nouveaux
# ══════════════════════════════════════════════════════════