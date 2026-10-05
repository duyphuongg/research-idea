from datetime import date, timedelta

from sqlalchemy import func, select

from app.keywords import get_or_create_keyword
from app.models import Keyword, KeywordRelation, KeywordScore, Seed, TrendSignal
from app.analysis.pod_filter import PodFilterRules
from app.pipeline.rescore import refilter, rescore
from app.pipeline.scan import run_scan

TODAY = date(2026, 10, 5)


def add_signal(session, text, source, metric, value, d):
    kw = get_or_create_keyword(session, text)
    session.add(TrendSignal(keyword_id=kw.id, source=source, metric=metric, value=value, date=d))
    return kw


def test_rescore_writes_one_row_per_keyword_and_replaces(session):
    a = add_signal(session, "nurse", "etsy", "views_per_day", 20.0, TODAY)
    add_signal(session, "nurse", "etsy", "views_per_day", 10.0, TODAY - timedelta(days=14))
    b = add_signal(session, "dog mom", "etsy", "views_per_day", 5.0, TODAY)
    add_signal(session, "old", "etsy", "views_per_day", 5.0, TODAY - timedelta(days=40))
    session.commit()

    assert rescore(session, TODAY) == 2
    session.commit()
    assert rescore(session, TODAY) == 2  # idempotent for the same day
    session.commit()

    rows = {r.keyword_id: r for r in session.scalars(select(KeywordScore))}
    assert set(rows) == {a.id, b.id}
    assert rows[a.id].date == TODAY
    assert rows[a.id].sources == ["etsy"]
    assert rows[a.id].score > rows[b.id].score


async def test_run_scan_rescores_after_connectors(session_factory):
    with session_factory() as s:
        add_signal(s, "nurse", "etsy", "views_per_day", 20.0, TODAY)
        s.commit()

    await run_scan(session_factory, [], today=TODAY)

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(KeywordScore)) == 1


def _disc(session, text, parent=None):
    kw = Keyword(text=text, origin="discovered", is_pod_relevant=True)
    session.add(kw)
    session.flush()
    if parent:
        p = get_or_create_keyword(session, parent)
        session.add(KeywordRelation(parent_id=p.id, child_id=kw.id, source="s", last_seen=TODAY))
    session.flush()
    return kw


def test_refilter_applies_new_blocklist_but_keeps_followed_and_seeds(session):
    a = _disc(session, "nurse bananas", "nurse")
    b = _disc(session, "dog mom bananas", "dog mom")
    session.add(Seed(keyword="dog mom bananas"))
    seed_kw = get_or_create_keyword(session, "nurse")
    session.commit()
    rules = PodFilterRules(blocklist=("bananas",), allow=frozenset({"nurse"}))

    assert refilter(session, rules=rules) == 1
    session.commit()
    assert a.is_pod_relevant is False
    assert b.is_pod_relevant is True
    assert seed_kw.is_pod_relevant is True
    assert refilter(session, rules=rules) == 0


def test_refilter_drops_existing_seed_plus_product_child(session):
    k = _disc(session, "nurse shirts", "nurse")
    ok = _disc(session, "nurse gift", "nurse")
    session.commit()
    assert refilter(session) == 1
    assert k.is_pod_relevant is False
    assert ok.is_pod_relevant is True


def test_rescore_runs_refilter_first(session):
    k = _disc(session, "nurse shirts", "nurse")
    session.commit()
    rescore(session, TODAY)
    assert k.is_pod_relevant is False
