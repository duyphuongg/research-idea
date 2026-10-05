from datetime import date, timedelta

from sqlalchemy import func, select

from app.keywords import get_or_create_keyword
from app.models import KeywordScore, TrendSignal
from app.pipeline.rescore import rescore
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
