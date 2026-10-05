from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import Connector
from app.db import utcnow
from app.models import ScanRun
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


async def execute_scan(app: Any, connectors: list[Connector]) -> list[int]:
    return await run_scan(
        app.state.session_factory,
        connectors,
        retention_days=app.state.settings.raw_retention_days,
    )
