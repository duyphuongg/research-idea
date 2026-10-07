"""One-shot daily scan, for running outside the web server (e.g. from a launchd job)."""

import logging

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.connectors.registry import ConnectorFactory, build_connectors
from app.pipeline.jobs import JobFactory, build_jobs
from app.pipeline.scan import run_scan
from app.services.scans import scan_in_progress
from app.settings_store import get_setting

logger = logging.getLogger(__name__)


async def run_daily_scan(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    connector_factory: ConnectorFactory = build_connectors,
    job_factory: JobFactory = build_jobs,
) -> list[int] | None:
    """Scan every enabled source once. Returns scan run ids, or None if another scan is running."""
    with session_factory() as session:
        if scan_in_progress(session):
            logger.info("Skipping daily scan: another scan is running")
            return None
        overrides = get_setting(session, "connectors_enabled")
    connectors = connector_factory(settings, overrides, None)
    jobs = job_factory(settings, overrides, None)
    if not connectors and not jobs:
        logger.info("Skipping daily scan: no enabled sources")
        return []
    return await run_scan(
        session_factory, connectors, jobs=jobs, retention_days=settings.raw_retention_days
    )
