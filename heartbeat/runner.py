"""
heartbeat/runner.py — V2.1
Lance le heartbeat au démarrage de l'app.
Tourne en arrière-plan toutes les 5 minutes.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
from config.settings import HEARTBEAT_INTERVAL_MIN

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
_job_error_counts: dict[str, int] = {}
_JOB_ERROR_ALERT_THRESHOLD = 3


def _on_job_event(event):
    """ARC-7 : Log et alerte si un job échoue ou est manqué répétitivement."""
    job_id = event.job_id
    if event.exception:
        _job_error_counts[job_id] = _job_error_counts.get(job_id, 0) + 1
        count = _job_error_counts[job_id]
        logger.error(
            f"[Heartbeat] Job '{job_id}' échoué (#{count}): {event.exception}"
        )
        if count >= _JOB_ERROR_ALERT_THRESHOLD:
            logger.critical(
                f"[Heartbeat] ⚠️ Job '{job_id}' a échoué {count} fois de suite ! "
                f"Vérifie les logs Railway."
            )
    else:
        # Job missed (scheduler surchargé)
        logger.warning(f"[Heartbeat] Job '{job_id}' manqué (scheduler surchargé ?)")


def start_heartbeat():
    global _scheduler
    from heartbeat.checklist import run_checklist
    from heartbeat.push_notifier import run_push_notifications  # ← AJOUT
    from memory.daily_distiller import run_distillation
    from core.session_manager import cleanup_inactive_sessions

    _scheduler = AsyncIOScheduler()

    # ARC-7 : listener pour les erreurs de jobs
    _scheduler.add_listener(_on_job_event, EVENT_JOB_ERROR | EVENT_JOB_MISSED)

    # Heartbeat principal toutes les 5 min
    _scheduler.add_job(
        run_checklist,
        trigger="interval",
        minutes=HEARTBEAT_INTERVAL_MIN,
        id="heartbeat",
        max_instances=1,
        misfire_grace_time=60,
    )

    # Push notifications toutes les 5 min        ← AJOUT
    _scheduler.add_job(
        run_push_notifications,
        trigger="interval",
        minutes=5,
        id="push_notifier",
        max_instances=1,
        misfire_grace_time=30,
    )

    # V2 : distillation nocturne à 2h00
    _scheduler.add_job(
        run_distillation,
        trigger="cron",
        hour=2,
        minute=0,
        id="daily_distiller",
        max_instances=1,
    )

    # V2 : nettoyage sessions inactives toutes les 30 min
    _scheduler.add_job(
        cleanup_inactive_sessions,
        trigger="interval",
        minutes=30,
        id="session_cleanup",
        max_instances=1,
    )

    _scheduler.start()
    logger.info(f"✅ Heartbeat démarré — toutes les {HEARTBEAT_INTERVAL_MIN} min | Distiller: 2h00 | Push: 5min")


def stop_heartbeat():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Heartbeat arrêté")