import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import Connector
from app.db import utcnow
from app.models import RawPayload, ScanRun, Seed
from app.pipeline.rescore import rescore
from app.pipeline.store import persist_batch

logger = logging.getLogger(__name__)
MAX_ERROR_LEN = 5000


async def run_scan(
    session_factory: sessionmaker[Session],
    connectors: list[Connector],
    *,
    today: date | None = None,
    retention_days: int = 30,
) -> list[int]:
    today = today or datetime.now(timezone.utc).date()
    with session_factory() as session:
        keywords = list(
            session.scalars(select(Seed.keyword).where(Seed.active.is_(True)).order_by(Seed.id))
        )

    run_ids = [await _run_one(session_factory, c, keywords, today) for c in connectors]

    try:
        with session_factory() as session:
            rescore(session, today)
            session.commit()
    except Exception:  # scoring must never break a scan
        logger.exception("Rescoring failed")

    with session_factory() as session:
        purge_raw_payloads(session, older_than=utcnow() - timedelta(days=retention_days))
        session.commit()
    return run_ids


async def _run_one(
    session_factory: sessionmaker[Session], connector: Connector, keywords: list[str], today: date
) -> int:
    with session_factory() as session:
        run = ScanRun(source=connector.name, status="running")
        session.add(run)
        session.commit()
        run_id = run.id

    status, records, error = "ok", 0, None
    try:
        raw = await connector.fetch(keywords)
        with session_factory() as session:  # keep raw payloads even if later steps fail
            for payload in raw.payloads:
                session.add(RawPayload(scan_run_id=run_id, source=connector.name, payload=payload))
            session.commit()
        normalized = connector.normalize(raw, today)
        with session_factory() as session:
            records = persist_batch(session, normalized, today)
            session.commit()
        if raw.errors:
            status = "partial" if raw.payloads else "failed"
            error = "\n".join(raw.errors)[:MAX_ERROR_LEN]
    except Exception as exc:  # isolate one connector's failure from the rest
        logger.exception("Connector %s failed", connector.name)
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LEN]

    try:
        with session_factory() as session:
            run = session.get(ScanRun, run_id)
            run.status = status
            run.records = records
            run.error = error
            run.finished_at = utcnow()
            session.commit()
    except Exception:
        logger.exception("Could not finalize scan run %s for %s", run_id, connector.name)
    return run_id


def purge_raw_payloads(session: Session, older_than: datetime) -> int:
    result = session.execute(delete(RawPayload).where(RawPayload.fetched_at < older_than))
    return result.rowcount or 0
