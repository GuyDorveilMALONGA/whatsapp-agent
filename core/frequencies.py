"""
core/frequencies.py — V1
Singleton fréquences estimées Dem Dikk.
Source : dem_dikk_frequencies.json

Expose :
  get_frequency(ligne) → dict | None
  format_service(ligne, langue, signalement_age_min) → str
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PATH = Path(__file__).parent.parent / "dem_dikk_frequencies.json"

try:
    with open(_PATH, encoding="utf-8") as f:
        _DATA = json.load(f)
    _LINES: dict = _DATA.get("lines", {})
    logger.info(f"[Frequencies] {len(_LINES)} lignes chargées")
except Exception as e:
    logger.error(f"[Frequencies] Erreur chargement: {e}")
    _LINES = {}

_PEAK_HOURS = [
    (7, 0, 9, 30),   # matin
    (17, 0, 20, 0),  # soir
]


def _is_peak() -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    h, m = now.hour, now.minute
    for dh, dm, fh, fm in _PEAK_HOURS:
        if (h * 60 + m) >= (dh * 60 + dm) and (h * 60 + m) <= (fh * 60 + fm):
            return True
    return False


def _is_in_service(ligne_data: dict) -> bool:
    """Vérifie si la ligne est actuellement en service."""
    try:
        service = ligne_data.get("service", {})
        debut = service.get("debut", "05:00")
        fin   = service.get("fin",   "23:00")
        now   = datetime.now(timezone.utc)
        h, m  = now.hour, now.minute
        current = h * 60 + m
        dh, dm = map(int, debut.split(":"))
        fh, fm = map(int, fin.split(":"))
        return (dh * 60 + dm) <= current <= (fh * 60 + fm)
    except Exception:
        return True  # par défaut : en service


def get_frequency(ligne: str) -> dict | None:
    """Retourne les données de fréquence pour une ligne ou None."""
    return _LINES.get(str(ligne).upper()) or _LINES.get(str(ligne))


def format_service(
    ligne: str,
    langue: str = "fr",
    signalement_age_min: int | None = None
) -> str:
    """
    Formate une réponse complète sur le service d'une ligne
    quand il n'y a pas de signalement actif.

    signalement_age_min : âge du dernier signalement en minutes (None = aucun)
    """
    data = get_frequency(ligne)

    if not data:
        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* — duma xam fréquence bi.\n"
                f"Signale bu nga ko gis ! 👀"
            )
        return (
            f"🚌 Bus *{ligne}* — pas d'info de fréquence disponible.\n"
            f"Sois le premier à le signaler ! 👀"
        )

    service  = data.get("service", {})
    debut    = service.get("debut", "?")
    fin      = service.get("fin",   "?")
    jours    = service.get("jours", "lun-dim")
    peak     = _is_peak()
    freq     = data["frequence_peak_min"] if peak else data["frequence_offpeak_min"]
    in_svc   = _is_in_service(data)
    note     = data.get("note", "")

    # Estimation prochaine arrivée basée sur fréquence
    # Si signalement récent : on peut estimer mieux
    # Estimation prudente — on ne peut pas promettre un temps précis
    if signalement_age_min is not None and signalement_age_min < freq:
        prochain = freq - signalement_age_min
        eta_str  = f"~{prochain} min _(basé sur dernier signalement, non garanti)_"
    else:
        eta_str = f"entre {freq // 2} et {freq} min _(estimation, non garanti)_"

    if not in_svc:
        if langue == "wolof":
            return (
                f"🚌 Bus *{ligne}* — service bi jeex.\n"
                f"Dëkk ak {debut} ci suba. 🌙"
            )
        return (
            f"🚌 Bus *{ligne}* — service terminé pour aujourd'hui.\n"
            f"Reprend à {debut} demain. 🌙"
        )

    if langue == "wolof":
        return (
            f"🚌 Bus *{ligne}* ({note})\n"
            f"⏰ Service : {debut} – {fin}\n"
            f"⏱ Fréquence : toutes les ~{freq} min {'(heure de pointe)' if peak else ''}\n"
            f"📍 Prochain estimé : {eta_str}\n"
            f"_Signale si tu le vois pour aider les autres !_ 👀"
        )

    return (
        f"🚌 Bus *{ligne}* — {note}\n"
        f"⏰ Service : {debut} – {fin} ({jours})\n"
        f"⏱ Fréquence : toutes les ~{freq} min {'⚡ heure de pointe' if peak else ''}\n"
        f"📍 Prochain estimé : {eta_str}\n"
        f"_Aucun signalement récent — sois le premier à le signaler !_ 👀\n"
        f"\n— *Xëtu*"
    )