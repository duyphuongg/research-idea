from app.db import utcnow

from app.config import Settings
from app.models import ScanRun
from app.services import hourly
from app.settings_store import set_setting


async def test_hourly_runs_job_alerts_and_telegram(session_factory, monkeypatch):
    calls = []

    async def fake_job(sf, key):
        calls.append(("job", key))
        with sf() as s:
            run = ScanRun(source="nfl_moments", status="ok")
            s.add(run)
            s.commit()
            return run.id

    async def fake_send(session, settings):
        calls.append(("send", None))

    monkeypatch.setattr(hourly, "run_nfl_moments", fake_job)
    monkeypatch.setattr(hourly, "send_pending", fake_send)
    run_id = await hourly.run_hourly(session_factory, Settings(etsy_api_key="k", _env_file=None))
    assert run_id is not None and calls == [("job", "k"), ("send", None)]


async def test_hourly_skips_when_disabled_or_busy(session_factory, monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("must not run")

    monkeypatch.setattr(hourly, "run_nfl_moments", boom)
    with session_factory() as s:
        set_setting(s, "connectors_enabled", {"nfl_moments": False})
        s.commit()
    assert await hourly.run_hourly(session_factory, Settings(_env_file=None)) is None
    with session_factory() as s:
        set_setting(s, "connectors_enabled", {})
        s.add(ScanRun(source="etsy", status="running", started_at=utcnow()))
        s.commit()
    assert await hourly.run_hourly(session_factory, Settings(_env_file=None)) is None
