from datetime import date, datetime, timedelta

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

    assert [c.name for c in build_connectors(configured, {})] == ["etsy", "google_suggest", "google_daily", "amazon"]
    assert [c.name for c in build_connectors(configured, {"etsy": False})] == ["google_suggest", "google_daily", "amazon"]
    assert [c.name for c in build_connectors(configured, {}, only=["amazon"])] == ["amazon"]
    assert [c.name for c in build_connectors(configured, {"amazon": False})] == ["etsy", "google_suggest", "google_daily"]
    assert [c.name for c in build_connectors(unconfigured, {})] == ["google_suggest", "google_daily", "amazon"]
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


class ReplacingConnector(FakeConnector):
    replace_daily_signals = True

    def __init__(self, phrases, name="repl"):
        super().__init__(name=name, products=[])
        self.phrases = phrases

    def normalize(self, raw, today):
        from app.connectors.base import NormalizedBatch, NormalizedSignal

        return NormalizedBatch(signals=[
            NormalizedSignal(p, self.name, "title_phrase_count", v, today, origin="discovered")
            for p, v in self.phrases.items()
        ])


async def test_replace_daily_signals_retracts_same_day_rows(session_factory):
    from app.models import Keyword, TrendSignal

    await run_scan(session_factory, [ReplacingConnector({"old phrase": 3, "keep": 4})], today=TODAY)
    await run_scan(session_factory, [ReplacingConnector({"keep": 5})], today=TODAY)
    with session_factory() as s:
        rows = {
            kw: v for kw, v in s.execute(
                select(Keyword.text, TrendSignal.value).join(TrendSignal, TrendSignal.keyword_id == Keyword.id)
                .where(TrendSignal.source == "repl")
            )
        }
    assert rows == {"keep": 5.0}


async def test_non_replacing_connector_keeps_old_signals(session_factory):
    from app.models import TrendSignal

    class Plain(ReplacingConnector):
        replace_daily_signals = False

    await run_scan(session_factory, [Plain({"a": 1})], today=TODAY)
    await run_scan(session_factory, [Plain({"b": 1})], today=TODAY)
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(TrendSignal)) == 2


async def test_replace_only_touches_own_source_date_and_metric(session_factory):
    from app.keywords import get_or_create_keyword
    from app.models import TrendSignal

    with session_factory() as s:
        kw = get_or_create_keyword(s, "x")
        for src, d, m in [("other", TODAY, "title_phrase_count"), ("repl", TODAY - timedelta(days=1), "title_phrase_count"), ("repl", TODAY, "other_metric")]:
            s.add(TrendSignal(keyword_id=kw.id, source=src, metric=m, value=1, date=d))
        s.commit()
    await run_scan(session_factory, [ReplacingConnector({"a": 1})], today=TODAY)
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(TrendSignal)) == 4


async def test_run_scan_uses_passed_settings_for_telegram(session_factory):
    import httpx
    import respx

    from app.models import Alert

    with session_factory() as s:
        s.add(Alert(kind="listing", subject_id=1, level=1, priority=1.0, title="Tee", reason="r",
                    image_url=None, link="/signals", external_url=None, watch_keyword=None,
                    scan_date=TODAY, created_at=utcnow()))
        # this week's digest already went out: only the alert notification is sent here
        from app.services.digest import iso_week
        from app.settings_store import set_setting
        set_setting(s, "digest_last_week", iso_week(datetime.now().astimezone().date()))
        s.commit()
    settings = Settings(_env_file=None, scheduler_enabled=False, telegram_bot_token="1:t", telegram_chat_id="42")
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post("https://api.telegram.org/bot1:t/sendMessage").mock(
            return_value=httpx.Response(200, json={"ok": True}))
        await run_scan(session_factory, [], today=TODAY, settings=settings)
    assert route.call_count == 1
    with session_factory() as s:
        from app.models import Alert as A
        assert s.scalar(select(A.sent_at)) is not None
