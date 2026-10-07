import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import Connector
from app.db import utcnow
from app.models import RawPayload, ScanRun, Seed, TrendSignal
from app.config import get_settings
from app.notify.telegram import send_pending
from app.pipeline.rescore import rescore
from app.pipeline.store import persist_batch
from app.services.alerts import detect_alerts

if TYPE_CHECKING:  # jobs imports listing_signals, which imports this module
    from app.pipeline.jobs import ScanJob

logger = logging.getLogger(__name__)
MAX_ERROR_LEN = 5000


async def run_scan(
    session_factory: sessionmaker[Session],
    connectors: list[Connector],
    *,
    jobs: Sequence["ScanJob"] = (),
    today: date | None = None,
    retention_days: int = 30,
) -> list[int]:
    today = today or datetime.now(timezone.utc).date()
    with session_factory() as session:
        keywords = list(
            session.scalars(select(Seed.keyword).where(Seed.active.is_(True)).order_by(Seed.id))
        )

    run_ids = [await _run_one(session_factory, c, keywords, today) for c in connectors]
    for job in jobs:
        try:  # the job records its own ScanRun
            run_ids.append(await job.run(session_factory, keywords, today))
        except Exception:
            logger.exception("Job %s failed", job.name)

    try:
        with session_factory() as session:
            rescore(session, today)
            session.commit()
    except Exception:  # scoring must never break a scan
        logger.exception("Rescoring failed")

    try:
        with session_factory() as session:
            detect_alerts(session, today)
            session.commit()
    except Exception:  # alerts must never break a scan
        logger.exception("Alert detection failed")

    try:
        with session_factory() as session:
            await send_pending(session, get_settings())
            session.commit()
    except Exception:  # Telegram must never break a scan
        logger.exception("Telegram delivery failed")

    with session_factory() as session:
        purge_raw_payloads(session, older_than=utcnow() - timedelta(days=retention_days))
        session.commit()
    return run_ids


def start_run(session_factory: sessionmaker[Session], source: str) -> int:
    with session_factory() as session:
        run = ScanRun(source=source, status="running")
        session.add(run)
        session.commit()
        return run.id


def finish_run(
    session_factory: sessionmaker[Session],
    run_id: int,
    source: str,
    status: str,
    records: int,
    error: str | None,
) -> None:
    try:
        with session_factory() as session:
            run = session.get(ScanRun, run_id)
            run.status = status
            run.records = records
            run.error = error
            run.finished_at = utcnow()
            session.commit()
    except Exception:
        logger.exception("Could not finalize scan run %s for %s", run_id, source)


async def _run_one(
    session_factory: sessionmaker[Session], connector: Connector, keywords: list[str], today: date
) -> int:
    run_id = start_run(session_factory, connector.name)

    status, records, error = "ok", 0, None
    try:
        raw = await connector.fetch(keywords)
        with session_factory() as session:  # keep raw payloads even if later steps fail
            for payload in raw.payloads:
                session.add(RawPayload(scan_run_id=run_id, source=connector.name, payload=payload))
            session.commit()
        normalized = connector.normalize(raw, today)
        with session_factory() as session:
            if getattr(connector, "replace_daily_signals", False):
                metrics = {sig.metric for sig in normalized.signals}
                if metrics:  # same-day rerun: retract rows this batch no longer produces
                    session.execute(
                        delete(TrendSignal).where(
                            TrendSignal.source == connector.name,
                            TrendSignal.date == today,
                            TrendSignal.metric.in_(metrics),
                        )
                    )
            records = persist_batch(session, normalized, today)
            session.commit()
        if raw.errors:
            status = "partial" if raw.payloads else "failed"
            error = "\n".join(raw.errors)[:MAX_ERROR_LEN]
    except Exception as exc:  # isolate one connector's failure from the rest
        logger.exception("Connector %s failed", connector.name)
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LEN]

    finish_run(session_factory, run_id, connector.name, status, records, error)
    return run_id


def purge_raw_payloads(session: Session, older_than: datetime) -> int:
    result = session.execute(delete(RawPayload).where(RawPayload.fetched_at < older_than))
    return result.rowcount or 0
