"""
heartbeat/runner.py
Lance le heartbeat au démarrage de l'app.
Tourne en arrière-plan toutes les 5 minutes.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config.settings import HEARTBEAT_INTERVAL_MIN

logger = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


def start_heartbeat():
    global _scheduler
    from heartbeat.checklist import run_checklist
    from memory.daily_distiller import run_distillation
    from core.session_manager import cleanup_inactive_sessions

    _scheduler = AsyncIOScheduler()

    # Heartbeat principal toutes les 5 min
    _scheduler.add_job(
        run_checklist,
        trigger="interval",
        minutes=HEARTBEAT_INTERVAL_MIN,
        id="heartbeat",
        max_instances=1,
        misfire_grace_time=60,
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
    logger.info(f"✅ Heartbeat démarré — toutes les {HEARTBEAT_INTERVAL_MIN} min | Distiller: 2h00")


def stop_heartbeat():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Heartbeat arrêté")
