"""
api/report.py — V1.1
Endpoint POST /api/report — signalement depuis le dashboard web.

MIGRATION V1.1 depuis V1.0 :
  - ReportPayload : champs lat / lon optionnels (coordonnées GPS passager)
  - nearest_stop  : champ optionnel (nom arrêt snapé côté client)
  - save_signalement() reçoit lat/lon si présents → stocké dans la table
  - source "web_geoloc" ajouté aux sources autorisées
  - Logs enrichis avec lat/lon quand présents

Sécurité :
  • Rate limit : 5 signalements / IP / 10 min (in-memory)
  • Rate limit : 30 signalements / IP / heure
  • Validation ligne ∈ VALID_LINES (Pydantic)
  • Sanitization champs texte (longueur max + strip + contrôles)
  • Déduplication 30s (même ligne+arrêt+IP → 200 idempotent)
  • Nettoyage automatique des structures in-memory toutes les 5 min

Réponses :
  201 → { "id": "rpt_xxx", "status": "recorded" }
  200 → { "status": "already_recorded" }
  422 → validation Pydantic (ligne invalide, arrêt trop court…)
  429 → { "error": "rate_limited", "retry_after": 120 }
  500 → { "error": "internal_error" }
"""

import logging
import re
import time
import hashlib
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from config.settings import VALID_LINES
from db import queries

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Rate limiting in-memory ───────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)
_RATE_LIMIT_SHORT = (5,  600)
_RATE_LIMIT_LONG  = (30, 3600)

# ── Déduplication 30s ─────────────────────────────────────
_recent_submissions: dict[str, float] = {}
_DEDUP_WINDOW_SEC = 30

# ── Nettoyage périodique ──────────────────────────────────
_last_cleanup = time.time()
_CLEANUP_INTERVAL = 300


# ── Payload ───────────────────────────────────────────────

class ReportPayload(BaseModel):
    ligne:        str
    arret:        str
    observation:  Optional[str]   = None
    source:       Optional[str]   = "web_dashboard"
    client_ts:    Optional[str]   = None
    session_id:   Optional[str]   = None
    # ── V1.1 : coordonnées GPS passager (optionnelles) ──
    lat:          Optional[float] = None
    lon:          Optional[float] = None
    nearest_stop: Optional[str]   = None   # arrêt snapé côté client

    @field_validator('ligne')
    @classmethod
    def validate_ligne(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("Ligne manquante")
        if v not in VALID_LINES:
            raise ValueError(f"Ligne inconnue : {v}")
        return v

    @field_validator('arret')
    @classmethod
    def validate_arret(cls, v: str) -> str:
        v = _sanitize(v, max_len=80)
        if len(v) < 2:
            raise ValueError("Arrêt trop court (minimum 2 caractères)")
        return v

    @field_validator('observation')
    @classmethod
    def validate_observation(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = _sanitize(v, max_len=200)
        return v if v else None

    @field_validator('source')
    @classmethod
    def validate_source(cls, v: Optional[str]) -> str:
        allowed = {
            "web_dashboard", "web_popup_confirm",
            "web_modal", "web_sheet",
            "web_geoloc",     # V1.1 — signalement avec coordonnées GPS
        }
        return v if v in allowed else "web_dashboard"

    @field_validator('lat')
    @classmethod
    def validate_lat(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        # Bounding box Sénégal élargie : lat 12–16, lon -17.7 à -11
        if not (12.0 <= v <= 16.0):
            raise ValueError(f"Latitude hors du Sénégal : {v}")
        return round(v, 6)

    @field_validator('lon')
    @classmethod
    def validate_lon(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if not (-17.7 <= v <= -11.0):
            raise ValueError(f"Longitude hors du Sénégal : {v}")
        return round(v, 6)

    @field_validator('nearest_stop')
    @classmethod
    def validate_nearest_stop(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _sanitize(v, max_len=80) or None


# ── Endpoint ──────────────────────────────────────────────

@router.post("/api/report", status_code=201)
async def post_report(request: Request, payload: ReportPayload):
    _maybe_cleanup()

    ip  = _get_client_ip(request)
    now = time.time()

    # Rate limit court (5 / 10 min)
    if not _check_rate(ip, now, _RATE_LIMIT_SHORT):
        logger.warning(f"[Report] Rate limit court — IP={ip[:20]}")
        return JSONResponse(
            status_code=429,
            content={
                "error":       "rate_limited",
                "message":     "Trop de signalements. Réessaie dans quelques minutes.",
                "retry_after": _RATE_LIMIT_SHORT[1],
            },
        )

    # Rate limit long (30 / heure)
    if not _check_rate(ip, now, _RATE_LIMIT_LONG):
        logger.warning(f"[Report] Rate limit long — IP={ip[:20]}")
        return JSONResponse(
            status_code=429,
            content={
                "error":       "rate_limited",
                "message":     "Quota horaire dépassé. Réessaie dans une heure.",
                "retry_after": _RATE_LIMIT_LONG[1],
            },
        )

    # Déduplication 30s
    dedup_key = _make_dedup_key(ip, payload.ligne, payload.arret)
    if dedup_key in _recent_submissions:
        elapsed = now - _recent_submissions[dedup_key]
        if elapsed < _DEDUP_WINDOW_SEC:
            logger.info(
                f"[Report] Doublon ({elapsed:.0f}s) "
                f"ligne={payload.ligne} arret={payload.arret}"
            )
            return JSONResponse(
                status_code=200,
                content={"status": "already_recorded"},
            )

    # Enregistrement
    try:
        phone_anon = f"web_{ip[:16]}"

        # V1.1 — passer lat/lon à save_signalement si disponibles
        save_kwargs = dict(
            ligne=payload.ligne,
            arret=payload.arret,
            phone=phone_anon,
        )
        if payload.lat is not None and payload.lon is not None:
            save_kwargs["lat"] = payload.lat
            save_kwargs["lon"] = payload.lon

        result = queries.save_signalement(**save_kwargs)

        if result is None:
            return JSONResponse(
                status_code=200,
                content={"status": "already_recorded"},
            )

        if payload.observation:
            try:
                queries.enrichir_signalement(
                    ligne=payload.ligne,
                    arret=payload.arret,
                    qualite=payload.observation,
                    phone=phone_anon,
                )
            except Exception as e:
                logger.warning(f"[Report] Enrichissement échoué: {e}")

        _record_rate(ip, now)
        _recent_submissions[dedup_key] = now

        report_id = f"rpt_{result.get('id', 'ok')}" if isinstance(result, dict) else "rpt_ok"

        # Log enrichi V1.1
        gps_info = f" lat={payload.lat} lon={payload.lon}" if payload.lat else " (pas de GPS)"
        logger.info(
            f"[Report] ✅ ligne={payload.ligne} arret={payload.arret} "
            f"obs={payload.observation} source={payload.source}{gps_info} "
            f"session={payload.session_id} ip={ip[:20]}"
        )

        return JSONResponse(
            status_code=201,
            content={"id": report_id, "status": "recorded"},
        )

    except Exception as e:
        logger.error(f"[Report] Erreur DB: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error"},
        )


# ── Helpers ───────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sanitize(text: str, max_len: int) -> str:
    text = text.strip()
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text[:max_len]


def _make_dedup_key(ip: str, ligne: str, arret: str) -> str:
    raw = f"{ip}:{ligne}:{arret.lower()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _check_rate(ip: str, now: float, limit_tuple: tuple) -> bool:
    max_req, window = limit_tuple
    key = f"{ip}:{window}"
    dq  = _rate_windows[key]
    while dq and now - dq[0] > window:
        dq.popleft()
    return len(dq) < max_req


def _record_rate(ip: str, now: float) -> None:
    for _, window in [_RATE_LIMIT_SHORT, _RATE_LIMIT_LONG]:
        _rate_windows[f"{ip}:{window}"].append(now)


def _maybe_cleanup() -> None:
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now

    expired = [k for k, t in _recent_submissions.items()
               if now - t > _DEDUP_WINDOW_SEC * 2]
    for k in expired:
        del _recent_submissions[k]

    empty = []
    for key, dq in _rate_windows.items():
        window = int(key.split(":")[-1])
        while dq and now - dq[0] > window:
            dq.popleft()
        if not dq:
            empty.append(key)
    for k in empty:
        del _rate_windows[k]

    logger.debug(f"[Report] Cleanup: {len(expired)} dedup, {len(empty)} rate windows purgés")
