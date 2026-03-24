"""
config/settings.py — V8.3
Point central — variables d'environnement, constantes, configuration globale.

MIGRATIONS V8.3 depuis V8.2 :
  - DEDUP_ARRET_WINDOW_MIN = 5 : fenêtre anti-doublon communautaire
    Après un signalement à un arrêt (toute source), le même arrêt+ligne
    est bloqué 5 min. Empêche les doublons communautaires (2 usagers
    voient le même bus à 1 min d'intervalle).

MIGRATIONS V8.2 depuis V8.1 :
  - JSON_PATH : pointe vers routes_geometry_v13_fixed2.json
  - EXCLUDED_LINES : set des lignes fantômes exclues de VALID_LINES

MIGRATIONS V8.1 depuis V8.0 :
  - JSON_PATH : chemin absolu via pathlib.Path(__file__) pour Railway

MIGRATIONS V8.0 depuis V7.0 :
  - VALID_LINES : généré dynamiquement depuis routes_geometry_v13.json
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
DATABASE_URL         = os.getenv("DATABASE_URL", "")

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
SIGNALEMENT_TTL_MINUTES  = 20
DEDUP_ARRET_WINDOW_MIN   = 5   # V8.3 : anti-doublon communautaire (même arrêt, toute source)
ANOMALIE_SEUIL_MINUTES   = 45
HEARTBEAT_INTERVAL_MIN   = 5
ALERTE_PROACTIVE_AVANT   = 15
HISTORIQUE_MESSAGES      = 10

# ── Sécurité ──────────────────────────────────────────────
# (RATE_LIMIT_PER_PHONE_PER_MIN défini une seule fois en haut)

# ── Business ──────────────────────────────────────────────
BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Xëtu")

# ── Chemin JSON réseau ────────────────────────────────────
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
# ══════════════════════════════════════════════════════════

# Lignes exclues (fantômes : 1 arrêt, données incomplètes)
EXCLUDED_LINES: set[str] = set(os.getenv("EXCLUDED_LINES", "").split(",")) - {""}

def _load_valid_lines() -> set[str]:
    try:
        with open(JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        lines = set()
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            num = props.get("route_short_name") or props.get("numero")
            if num:
                lines.add(str(num).upper().strip())
        if lines:
            lines -= EXCLUDED_LINES
            logger.info(f"[Settings] VALID_LINES chargées depuis JSON : {len(lines)} lignes")
            return lines
    except FileNotFoundError:
        logger.warning(f"[Settings] JSON introuvable ({JSON_PATH}), fallback V7")
    except Exception as e:
        logger.error(f"[Settings] Erreur chargement JSON : {e}, fallback V7")

    # Fallback V7 hardcodé
    fallback = {
        "1","2","3","4","5","6","7","8","9","10",
        "11","12","13","14","15","16A","16B","17","18","19","20",
        "21","22","23","24","25","26","27","28","29","30",
        "36","46","56","69","70","77","78","79",
        "100","101","102","103","104","105","106","107","108","109","110",
        "111","112","113","114","115","116","117","118","119","120",
        "121","200","201","202","203","204","205","206","207","208","209","210",
        "211","212","213","214","215","216","217","218","219","220",
        "DDD","TAF TAF","TO1","PETITE COTE",
    }
    fallback -= EXCLUDED_LINES
    logger.info(f"[Settings] VALID_LINES fallback V7 : {len(fallback)} lignes")
    return fallback


VALID_LINES: set[str] = _load_valid_lines()