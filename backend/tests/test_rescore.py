from datetime import datetime
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


def test_refilter_loads_rules_once(session, monkeypatch):
    import app.pipeline.rescore as mod

    _disc(session, "nurse gift", "nurse")
    _disc(session, "dog mom hat", "dog mom")
    session.commit()
    calls = []
    real = mod.load_rules
    monkeypatch.setattr(mod, "load_rules", lambda: calls.append(1) or real())
    monkeypatch.setattr(
        "app.analysis.pod_filter.load_rules", lambda: calls.append(1) or real()
    )
    refilter(session)
    assert len(calls) == 1


def _sig(session, kw, d, value, source="s", metric="m"):
    session.add(TrendSignal(keyword_id=kw.id, source=source, metric=metric, value=value, date=d))


def test_merge_duplicate_keywords_merges_into_canonical(session):
    from app.models import Product, ProductKeyword
    from app.pipeline.rescore import merge_duplicate_keywords

    dup = _disc(session, "nurse gifts", "nurse")
    target = _disc(session, "nurse gift", "nurse")
    other = _disc(session, "rn")
    d1, d2 = TODAY, TODAY - timedelta(days=1)
    _sig(session, dup, d1, 9.0)
    _sig(session, target, d1, 5.0)
    _sig(session, dup, d2, 2.0)
    session.add(KeywordRelation(parent_id=dup.id, child_id=other.id, source="s", last_seen=TODAY))
    session.add(KeywordScore(keyword_id=dup.id, date=TODAY, score=1.0))
    p = Product(source="etsy", external_id="1", title="t", url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add(ProductKeyword(product_id=p.id, keyword_id=dup.id, rank=1, last_seen=TODAY))
    session.add(ProductKeyword(product_id=p.id, keyword_id=target.id, rank=4, last_seen=d2))
    dup.first_seen_at = datetime(2020, 1, 1)
    session.commit()
    target_id, dup_id, other_id = target.id, dup.id, other.id

    assert merge_duplicate_keywords(session) == 1
    session.commit()

    assert session.scalar(select(Keyword).where(Keyword.text == "nurse gifts")) is None
    assert session.get(Keyword, dup_id) is None
    t = session.get(Keyword, target_id)
    assert t.first_seen_at == datetime(2020, 1, 1)
    sigs = {s.date: s.value for s in session.scalars(select(TrendSignal).where(TrendSignal.keyword_id == target_id))}
    assert sigs == {d1: 9.0, d2: 2.0}
    rel = session.scalars(select(KeywordRelation).where(KeywordRelation.child_id == other_id)).all()
    assert [r.parent_id for r in rel] == [target_id]
    # parent "nurse" -> dup child collapsed into existing target relation
    assert session.scalar(
        select(func.count()).select_from(KeywordRelation).where(KeywordRelation.child_id == target_id)
    ) == 1
    assert session.scalar(select(func.count()).select_from(KeywordScore)) == 0
    pk = session.scalars(select(ProductKeyword)).all()
    assert len(pk) == 1 and pk[0].keyword_id == target_id and pk[0].rank == 1 and pk[0].last_seen == TODAY


def test_merge_duplicate_keywords_renames_lone_and_skips_seeds(session):
    from app.pipeline.rescore import merge_duplicate_keywords

    lone = _disc(session, "dog mom gifts")
    seeded = _disc(session, "dog moms")
    session.add(Seed(keyword="dog moms"))
    session.commit()

    assert merge_duplicate_keywords(session) == 1
    session.commit()
    assert lone.text == "dog mom gift"
    assert seeded.text == "dog moms"


def test_merge_then_rescore_idempotent(session):
    from app.pipeline.rescore import merge_duplicate_keywords

    a = _disc(session, "nurse gifts", "nurse")
    b = _disc(session, "nurse gift", "nurse")
    _sig(session, a, TODAY, 9.0, "etsy", "views_per_day")
    _sig(session, b, TODAY, 5.0, "etsy", "views_per_day")
    session.commit()
    rescore(session, TODAY)
    session.commit()
    assert merge_duplicate_keywords(session) == 0
    n = session.scalar(select(func.count()).select_from(Keyword))
    rescore(session, TODAY)
    session.commit()
    assert session.scalar(select(func.count()).select_from(Keyword)) == n


def test_refilter_keeps_trusted_source_keyword_relevant(session):
    kw = Keyword(text="vintage sasquatch", origin="discovered", is_pod_relevant=True)
    session.add(kw)
    session.flush()
    session.add(TrendSignal(keyword_id=kw.id, source="etsy_signals", metric="breakout_tag_count", value=2.0, date=TODAY))
    session.commit()

    refilter(session, rules=PodFilterRules(blocklist=(), allow=frozenset()))

    assert kw.is_pod_relevant is True
