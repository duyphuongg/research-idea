from datetime import timedelta

from app.db import utcnow
from app.models import ScanRun, Seed
from app.pipeline.jobs import ScanJob
from app.services.daily import hours_since_last_scan, run_daily_scan
from app.settings_store import set_setting
from tests.fakes import FakeConnector


async def test_runs_enabled_connectors_and_jobs(session_factory, settings):
    with session_factory() as s:
        s.add(Seed(keyword="nurse"))
        set_setting(s, "connectors_enabled", {"google_daily": False})
        s.commit()
    seen = {}
    job_calls = []

    def connector_factory(cfg, overrides, only):
        seen["overrides"], seen["only"] = overrides, only
        return [FakeConnector()]

    async def job(sf, keywords, today):
        job_calls.append(keywords)
        with sf() as s:
            run = ScanRun(source="job", status="ok", finished_at=utcnow())
            s.add(run)
            s.commit()
            return run.id

    run_ids = await run_daily_scan(
        session_factory,
        settings,
        connector_factory=connector_factory,
        job_factory=lambda cfg, overrides, only: [ScanJob("job", job)],
    )

    assert seen == {"overrides": {"google_daily": False}, "only": None}
    assert job_calls == [["nurse"]]
    with session_factory() as s:
        assert sorted(s.get(ScanRun, i).source for i in run_ids) == ["fake", "job"]


async def test_skips_when_a_scan_is_running(session_factory, settings):
    with session_factory() as s:
        s.add(ScanRun(source="etsy", status="running", started_at=utcnow()))
        s.commit()
    called = []
    result = await run_daily_scan(
        session_factory,
        settings,
        connector_factory=lambda *a: called.append("c") or [FakeConnector()],
        job_factory=lambda *a: [],
    )
    assert result is None and called == []


async def test_no_enabled_sources_returns_empty(session_factory, settings):
    result = await run_daily_scan(
        session_factory, settings, connector_factory=lambda *a: [], job_factory=lambda *a: []
    )
    assert result == []


def test_hours_since_last_scan_ignores_hourly_moments(session_factory):
    now = utcnow()
    with session_factory() as s:
        assert hours_since_last_scan(s, now=now) is None
        s.add(ScanRun(source="etsy", status="ok", started_at=now - timedelta(hours=30)))
        s.add(ScanRun(source="nfl_moments", status="ok", started_at=now - timedelta(hours=1)))
        s.commit()
        assert round(hours_since_last_scan(s, now=now)) == 30
