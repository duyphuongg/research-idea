from datetime import date, timedelta

from sqlalchemy import func, select

from app.config import Settings
from app.connectors.registry import build_connectors, connector_status
from app.db import utcnow
from app.models import Product, ProductSnapshot, RawPayload, ScanRun, Seed
from app.pipeline.jobs import ScanJob
from app.pipeline.scan import run_scan
from app.services.scans import mark_interrupted_scans
from tests.fakes import FakeConnector

TODAY = date(2026, 10, 5)


def add_seeds(session_factory, *keywords, inactive=()):
    with session_factory() as s:
        s.add_all([Seed(keyword=k) for k in keywords])
        s.add_all([Seed(keyword=k, active=False) for k in inactive])
        s.commit()


async def test_run_scan_persists_and_marks_ok(session_factory):
    add_seeds(session_factory, "nurse", "dog mom", inactive=["old"])
    fake = FakeConnector()

    [run_id] = await run_scan(session_factory, [fake], today=TODAY)

    assert fake.received_keywords == ["nurse", "dog mom"]
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert (run.source, run.status, run.records, run.error) == ("fake", "ok", 1, None)
        assert run.finished_at is not None
        assert s.scalar(select(func.count()).select_from(Product)) == 1
        assert s.scalar(select(ProductSnapshot)).date == TODAY
        assert s.scalar(select(RawPayload)).payload == {"keywords": ["nurse", "dog mom"]}


async def test_failing_connector_does_not_stop_others(session_factory):
    add_seeds(session_factory, "nurse")
    ids = await run_scan(
        session_factory, [FakeConnector(name="bad", fail=True), FakeConnector(name="good")], today=TODAY
    )

    with session_factory() as s:
        bad, good = (s.get(ScanRun, i) for i in ids)
        assert bad.status == "failed"
        assert "RuntimeError: boom" in bad.error
        assert good.status == "ok"


async def test_errors_with_payloads_mark_partial(session_factory):
    add_seeds(session_factory, "nurse")
    [run_id] = await run_scan(
        session_factory, [FakeConnector(errors=["nurse hoodie: HTTP 500"])], today=TODAY
    )

    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "partial"
        assert "HTTP 500" in run.error


async def test_old_raw_payloads_are_purged(session_factory):
    with session_factory() as s:
        run = ScanRun(source="fake", status="ok")
        s.add(run)
        s.flush()
        s.add(RawPayload(scan_run_id=run.id, source="fake", payload={}, fetched_at=utcnow() - timedelta(days=40)))
        s.add(RawPayload(scan_run_id=run.id, source="fake", payload={}, fetched_at=utcnow() - timedelta(days=1)))
        s.commit()

    await run_scan(session_factory, [], today=TODAY, retention_days=30)

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(RawPayload)) == 1


def test_registry_filters_unconfigured_and_disabled():
    configured = Settings(etsy_api_key="k", _env_file=None)
    unconfigured = Settings(etsy_api_key=None, _env_file=None)

    assert [c.name for c in build_connectors(configured, {})] == ["etsy", "google_suggest", "google_daily"]
    assert [c.name for c in build_connectors(configured, {"etsy": False})] == ["google_suggest", "google_daily"]
    assert build_connectors(configured, {}, only=["amazon"]) == []
    assert [c.name for c in build_connectors(unconfigured, {})] == ["google_suggest", "google_daily"]
    assert connector_status(unconfigured, {"etsy": False})[0] == {
        "name": "etsy", "kind": "product", "configured": False, "enabled": False
    }


class NormalizeFails(FakeConnector):
    def normalize(self, raw, today):
        raise ValueError("bad payload")


async def test_raw_payloads_kept_when_normalize_raises(session_factory):
    add_seeds(session_factory, "nurse")

    [run_id] = await run_scan(session_factory, [NormalizeFails()], today=TODAY)

    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed"
        assert "ValueError" in run.error
        assert s.scalar(
            select(func.count()).select_from(RawPayload).where(RawPayload.scan_run_id == run_id)
        ) == 1


def test_mark_interrupted_scans(session):
    session.add_all([ScanRun(source="a", status="running"), ScanRun(source="b", status="ok")])
    session.commit()

    assert mark_interrupted_scans(session) == 1
    session.commit()

    a, b = session.scalars(select(ScanRun).order_by(ScanRun.id))
    assert (a.status, a.error) == ("failed", "interrupted (process restart)")
    assert a.finished_at is not None
    assert b.status == "ok"


async def test_run_scan_runs_jobs_with_keywords_and_collects_ids(session_factory):
    add_seeds(session_factory, "nurse")
    calls = []

    async def fake_run(sf, keywords, today):
        calls.append((sf, keywords, today))
        return 99

    ids = await run_scan(session_factory, [], jobs=[ScanJob("j", fake_run)], today=TODAY)

    assert calls == [(session_factory, ["nurse"], TODAY)]
    assert ids == [99]


async def test_failing_job_does_not_stop_rescore(session_factory):
    from app.keywords import get_or_create_keyword
    from app.models import KeywordScore, TrendSignal

    with session_factory() as s:
        kw = get_or_create_keyword(s, "nurse")
        s.add(TrendSignal(keyword_id=kw.id, source="etsy", metric="views_per_day", value=5.0, date=TODAY))
        s.commit()

    async def boom(sf, keywords, today):
        raise RuntimeError("nope")

    ids = await run_scan(session_factory, [], jobs=[ScanJob("j", boom)], today=TODAY)

    assert ids == []
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(KeywordScore)) == 1
