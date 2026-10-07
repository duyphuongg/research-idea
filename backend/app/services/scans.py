from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import Connector
from app.db import utcnow
from app.models import ScanRun
from app.pipeline.jobs import ScanJob
from app.pipeline.scan import run_scan
from app.settings_store import get_setting

RUNNING_STALE_AFTER = timedelta(hours=1)


def scan_in_progress(session: Session) -> bool:
    cutoff = utcnow() - RUNNING_STALE_AFTER
    running = session.scalar(
        select(func.count())
        .select_from(ScanRun)
        .where(ScanRun.status == "running", ScanRun.started_at >= cutoff)
    )
    return bool(running)


def resolve_connectors(app: Any, session: Session, only: list[str] | None = None) -> list[Connector]:
    overrides = get_setting(session, "connectors_enabled")
    return app.state.connector_factory(app.state.settings, overrides, only)


def resolve_jobs(app: Any, session: Session, only: list[str] | None = None) -> list[ScanJob]:
    overrides = get_setting(session, "connectors_enabled")
    return app.state.job_factory(app.state.settings, overrides, only)


def try_begin_scan(app: Any) -> bool:
    return app.state.scan_lock.acquire(blocking=False)


async def execute_scan(
    app: Any, connectors: list[Connector], jobs: Sequence[ScanJob] = ()
) -> list[int]:
    """Run a scan; the caller must already hold the lock from try_begin_scan."""
    try:
        return await run_scan(
            app.state.session_factory,
            connectors,
            jobs=jobs,
            retention_days=app.state.settings.raw_retention_days,
        )
    finally:
        app.state.scan_lock.release()


def mark_interrupted_scans(session: Session) -> int:
    """Fail scans left 'running' by a stopped process; the caller commits."""
    runs = list(session.scalars(select(ScanRun).where(ScanRun.status == "running")))
    for run in runs:
        run.status = "failed"
        run.error = "interrupted (process restart)"
        run.finished_at = utcnow()
    return len(runs)
