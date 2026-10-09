"""Hourly job (launchd): NFL moments from Google Trends, their alerts and Telegram delivery."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.notify.telegram import send_pending
from app.pipeline.nfl_moments import SOURCE, run_nfl_moments
from app.services.alerts import detect_moment_alerts
from app.services.scans import scan_in_progress
from app.settings_store import get_setting

logger = logging.getLogger(__name__)


async def run_hourly(session_factory: sessionmaker[Session], settings: Settings) -> int | None:
    """Returns the scan run id, or None when skipped (disabled in Settings or another scan is running)."""
    with session_factory() as session:
        if not (get_setting(session, "connectors_enabled") or {}).get(SOURCE, True):
            logger.info("Skipping hourly NFL moments: disabled in Settings")
            return None
        if scan_in_progress(session):
            logger.info("Skipping hourly NFL moments: a scan is running")
            return None
    run_id = await run_nfl_moments(session_factory, settings.etsy_api_key)
    try:
        with session_factory() as session:
            detect_moment_alerts(session)
            session.commit()
    except Exception:  # alerts must never break the job
        logger.exception("NFL moment alerts failed")
    try:
        with session_factory() as session:
            try:
                await send_pending(session, settings)
            finally:  # keep sent_at for alerts already delivered
                session.commit()
    except Exception:
        logger.exception("Telegram delivery failed")
    return run_id
