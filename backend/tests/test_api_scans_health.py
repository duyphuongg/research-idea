from app.db import utcnow
from app.models import ScanRun
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
    session.add(ScanRun(source="fake", status="running", started_at=utcnow()))
    session.commit()
    client = make_client(connector_factory=lambda s, o, only: [FakeConnector()])
    assert client.post("/api/scans", json={}).status_code == 409


def test_start_scan_requires_enabled_connector(make_client):
    client = make_client(connector_factory=lambda s, o, only: [])
    assert client.post("/api/scans", json={}).status_code == 400


def test_source_health_reports_last_finished_run(client, session):
    session.add(ScanRun(source="etsy", status="ok", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="failed", error="HTTP 403", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="running"))
    session.commit()

    [etsy] = client.get("/api/health/sources").json()
    assert etsy["name"] == "etsy"
    assert etsy["configured"] is True
    assert etsy["last_status"] == "failed"
    assert etsy["last_error"] == "HTTP 403"
    assert etsy["last_finished_at"] is not None
