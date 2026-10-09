from sqlalchemy import select

from app.db import utcnow
from app.models import ScanRun
from app.pipeline.jobs import ScanJob
from tests.fakes import FakeConnector


def test_start_scan_runs_in_background(make_client, session):
    fake = FakeConnector()
    client = make_client(connector_factory=lambda settings, overrides, only: [fake])

    resp = client.post("/api/scans", json={})
    assert resp.status_code == 202
    assert resp.json() == {"sources": ["fake"]}

    runs = client.get("/api/scans").json()
    assert len(runs) == 1
    assert runs[0]["source"] == "fake"
    assert runs[0]["status"] == "ok"
    assert runs[0]["records"] == 1


def test_start_scan_passes_requested_sources(make_client):
    seen = {}

    def factory(settings, overrides, only):
        seen["only"] = only
        return [FakeConnector()]

    client = make_client(connector_factory=factory)
    client.post("/api/scans", json={"sources": ["etsy"]})
    assert seen["only"] == ["etsy"]


def test_start_scan_conflicts_when_running(make_client, session):
    client = make_client(connector_factory=lambda s, o, only: [FakeConnector()])
    session.add(ScanRun(source="fake", status="running", started_at=utcnow()))
    session.commit()
    assert client.post("/api/scans", json={}).status_code == 409


def test_start_scan_conflicts_while_lock_held(make_client):
    client = make_client(connector_factory=lambda s, o, only: [FakeConnector()])
    lock = client.app.state.scan_lock
    assert lock.acquire(blocking=False)
    try:
        assert client.post("/api/scans", json={}).status_code == 409
    finally:
        lock.release()
    assert client.post("/api/scans", json={}).status_code == 202


def test_scan_lock_released_after_background_scan(make_client):
    client = make_client(connector_factory=lambda s, o, only: [FakeConnector()])
    assert client.post("/api/scans", json={}).status_code == 202
    lock = client.app.state.scan_lock
    assert lock.acquire(blocking=False)
    lock.release()


def test_start_scan_requires_enabled_connector(make_client):
    client = make_client(connector_factory=lambda s, o, only: [])
    assert client.post("/api/scans", json={}).status_code == 400


def test_source_health_reports_last_finished_run(client, session):
    session.add(ScanRun(source="etsy", status="ok", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="failed", error="HTTP 403", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="running"))
    session.commit()

    etsy = next(s for s in client.get("/api/health/sources").json() if s["name"] == "etsy")
    assert etsy["name"] == "etsy"
    assert etsy["configured"] is True
    assert etsy["last_status"] == "failed"
    assert etsy["last_error"] == "HTTP 403"
    assert etsy["last_finished_at"] is not None


def test_startup_marks_running_scans_failed(session_factory, make_client):
    with session_factory() as s:
        s.add(ScanRun(source="etsy", status="running"))
        s.commit()

    make_client()

    with session_factory() as s:
        run = s.scalar(select(ScanRun))
        assert run.status == "failed"
        assert run.error == "interrupted (process restart)"
        assert run.finished_at is not None


def test_start_scan_runs_jobs_only(make_client):
    async def fake(sf, keywords, today):
        return 1

    client = make_client(
        connector_factory=lambda *a: [], job_factory=lambda *a: [ScanJob("etsy_signals", fake)]
    )
    resp = client.post("/api/scans", json={})
    assert resp.status_code == 202
    assert resp.json()["sources"] == ["etsy_signals"]


def test_start_scan_requires_connector_or_job(make_client):
    client = make_client(connector_factory=lambda *a: [], job_factory=lambda *a: [])
    assert client.post("/api/scans", json={}).status_code == 400


def test_start_scan_selects_connectors_and_jobs_by_source(make_client):
    async def noop(sf, kw, today):
        return 0

    def connectors(settings, overrides, only):
        return [FakeConnector(name="etsy")] if only is None or "etsy" in only else []

    def jobs(settings, overrides, only):
        return [ScanJob("etsy_signals", noop)] if only is None or "etsy_signals" in only else []

    client = make_client(connector_factory=connectors, job_factory=jobs)

    resp = client.post("/api/scans", json={"sources": ["etsy"]})
    assert resp.status_code == 202
    assert resp.json() == {"sources": ["etsy"]}

    resp = client.post("/api/scans", json={"sources": ["etsy_signals"]})
    assert resp.status_code == 202
    assert resp.json() == {"sources": ["etsy_signals"]}


def test_source_health_has_no_amazon(client):
    names = [s["name"] for s in client.get("/api/health/sources").json()]
    assert names == ["etsy", "google_suggest", "google_daily", "etsy_signals", "etsy_counts", "nfl", "nfl_moments"]
