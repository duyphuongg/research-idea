import threading
from types import SimpleNamespace

from sqlalchemy import select

from app.config import Settings
from app.db import utcnow
from app.models import ScanRun, Seed
from app.scheduler import JOB_ID, reschedule, scheduled_scan, start_scheduler
from app.settings_store import set_setting
from tests.fakes import FakeConnector


def _scan_app(session_factory, fake):
    settings = Settings(etsy_api_key="k", scheduler_enabled=False, _env_file=None)
    return SimpleNamespace(
        state=SimpleNamespace(
            session_factory=session_factory,
            settings=settings,
            connector_factory=lambda s, o, only: [fake],
            job_factory=lambda s, o, only: [],
            scan_lock=threading.Lock(),
        )
    )


def _runs(session_factory):
    with session_factory() as s:
        return list(s.scalars(select(ScanRun)))


async def test_scheduled_scan_runs_and_releases_lock(session_factory):
    with session_factory() as s:
        s.add(Seed(keyword="nurse"))
        s.commit()
    fake = FakeConnector()
    app = _scan_app(session_factory, fake)
    await scheduled_scan(app)

    [run] = _runs(session_factory)
    assert (run.source, run.status) == ("fake", "ok")
    assert app.state.scan_lock.acquire(blocking=False)


async def test_scheduler_uses_stored_hour_and_reschedules(session_factory):
    with session_factory() as s:
        set_setting(s, "scan_hour_utc", 5)
        s.commit()
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))

    scheduler = start_scheduler(app)
    try:
        assert app.state.scheduler is scheduler
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 5
        reschedule(app, 3)
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 3
    finally:
        scheduler.shutdown(wait=False)


def test_reschedule_without_scheduler_is_noop():
    reschedule(SimpleNamespace(state=SimpleNamespace()), 3)


async def test_scheduled_scan_skips_when_scan_running(session_factory):
    with session_factory() as s:
        s.add(Seed(keyword="nurse"))
        s.add(ScanRun(source="fake", status="running", started_at=utcnow()))
        s.commit()
    fake = FakeConnector()
    app = _scan_app(session_factory, fake)

    await scheduled_scan(app)

    assert len(_runs(session_factory)) == 1
    assert fake.received_keywords is None


async def test_scheduled_scan_skips_when_lock_held(session_factory):
    with session_factory() as s:
        s.add(Seed(keyword="nurse"))
        s.commit()
    fake = FakeConnector()
    app = _scan_app(session_factory, fake)
    app.state.scan_lock.acquire()

    await scheduled_scan(app)

    assert _runs(session_factory) == []
    assert fake.received_keywords is None
