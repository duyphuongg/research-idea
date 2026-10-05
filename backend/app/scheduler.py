import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.scans import execute_scan, resolve_connectors, scan_in_progress, try_begin_scan
from app.settings_store import get_setting

logger = logging.getLogger(__name__)
JOB_ID = "daily_scan"


def _trigger(hour: int) -> CronTrigger:
    return CronTrigger(hour=hour, minute=0, timezone="UTC")


async def scheduled_scan(app: Any) -> None:
    try:
        with app.state.session_factory() as session:
            if scan_in_progress(session):
                logger.info("Skipping scheduled scan: another scan is running")
                return
            connectors = resolve_connectors(app, session)
        if not connectors:
            logger.info("Skipping scheduled scan: no enabled connectors")
            return
        if not try_begin_scan(app):
            logger.info("Skipping scheduled scan: another scan is starting")
            return
        await execute_scan(app, connectors)
    except Exception:
        logger.exception("Scheduled scan failed")


def start_scheduler(app: Any) -> AsyncIOScheduler:
    with app.state.session_factory() as session:
        hour = get_setting(session, "scan_hour_utc")
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_scan,
        _trigger(hour),
        id=JOB_ID,
        args=[app],
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler


def reschedule(app: Any, hour: int) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.reschedule_job(JOB_ID, trigger=_trigger(hour))
