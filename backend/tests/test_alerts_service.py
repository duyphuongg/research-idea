from datetime import date, datetime

from sqlalchemy import select

from app.analysis.alerts import AlertsConfig
from app.keywords import get_or_create_keyword
from app.models import (
    Alert, AmazonRank, KeywordRelation, KeywordScore, ListingSignal, Product, Seed,
)
from app.services.alerts import detect_alerts

TODAY = date(2026, 10, 8)
NOW = datetime(2026, 10, 8, 13, 0)


def _product(session, ext, title, source="etsy", licensed=False):
    p = Product(source=source, external_id=ext, title=title, url=f"https://x/{ext}",
                image_url=f"https://img/{ext}.jpg", product_type="tshirt", licensed=licensed)
    session.add(p)
    session.flush()
    return p


def test_detects_niche_listing_and_amazon(session):
    session.add(Seed(keyword="game day"))
    seed_kw = get_or_create_keyword(session, "game day")
    child = get_or_create_keyword(session, "game day vibes", origin="discovered", has_parent=True)
    session.add(KeywordRelation(parent_id=seed_kw.id, child_id=child.id, source="etsy", last_seen=TODAY))
    session.add(KeywordScore(keyword_id=child.id, score=70, growth=0.5, date=TODAY))
    session.add(KeywordScore(keyword_id=seed_kw.id, score=40, growth=0.5, date=TODAY))

    lp = _product(session, "l1", "Game Day Vibes Tee")
    session.add(ListingSignal(product_id=lp.id, discovered_on=TODAY, discovery_query="graphic tee",
                              status="steady_grower", delta_saves=6, dsr=0.1, updated_on=TODAY))
    other = _product(session, "l2", "Cat Tee")
    session.add(ListingSignal(product_id=other.id, discovered_on=TODAY, discovery_query="graphic tee",
                              status="steady_grower", delta_saves=9, dsr=0.1, updated_on=TODAY))

    a_new = _product(session, "a1", "Funny Tee", source="amazon")
    a_old = _product(session, "a2", "Old Tee", source="amazon")
    a_lic = _product(session, "a3", "NFL Tee", source="amazon", licensed=True)
    prev = date(2026, 10, 7)
    session.add_all([
        AmazonRank(product_id=a_old.id, date=prev, category_key="women_tshirts", list_name="bestsellers", rank=5),
        AmazonRank(product_id=a_new.id, date=prev, category_key="women_tshirts", list_name="bestsellers", rank=40),
        AmazonRank(product_id=a_old.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=4),
        AmazonRank(product_id=a_new.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=9),
        AmazonRank(product_id=a_lic.id, date=TODAY, category_key="women_tshirts", list_name="bestsellers", rank=1),
    ])
    session.flush()

    alerts = detect_alerts(session, TODAY, AlertsConfig(), NOW)
    got = sorted((a.kind, a.subject_id) for a in alerts)
    assert got == sorted([("niche", child.id), ("listing", lp.id), ("amazon", a_new.id)])
    listing = next(a for a in alerts if a.kind == "listing")
    assert listing.watch_keyword == "game day"
    assert listing.link == "/signals?keyword=game+day&status=all"


def test_second_run_is_deduped(session):
    p = _product(session, "s1", "Anything")
    session.add(ListingSignal(product_id=p.id, discovered_on=TODAY, discovery_query="shirt",
                              status="super_breakout", delta_saves=20, dsr=0.3, updated_on=TODAY))
    session.flush()
    assert len(detect_alerts(session, TODAY, AlertsConfig(), NOW)) == 1
    assert detect_alerts(session, TODAY, AlertsConfig(), NOW) == []
    assert session.scalar(select(Alert.link)) == "/signals?status=super_breakout"


def test_no_amazon_alerts_without_previous_day(session):
    a = _product(session, "a9", "Tee", source="amazon")
    session.add(AmazonRank(product_id=a.id, date=TODAY, category_key="men_tshirts", list_name="bestsellers", rank=1))
    session.flush()
    assert detect_alerts(session, TODAY, AlertsConfig(), NOW) == []


async def test_run_scan_survives_alert_failure(session_factory, monkeypatch):
    from app.pipeline import scan as scan_mod
    from tests.fakes import FakeConnector

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_mod, "detect_alerts", boom)
    run_ids = await scan_mod.run_scan(session_factory, [FakeConnector()])
    assert len(run_ids) == 1


def test_amazon_previous_date_is_per_category(session):
    a_new = _product(session, "pa1", "New A", source="amazon")
    b_any = _product(session, "pb1", "New B", source="amazon")
    prev = date(2026, 10, 7)
    session.add_all([
        AmazonRank(product_id=a_new.id, date=prev, category_key="cat_a", list_name="bestsellers", rank=50),
        AmazonRank(product_id=a_new.id, date=TODAY, category_key="cat_a", list_name="bestsellers", rank=3),
        # cat_b is new today: no previous date, so nothing in it can be "new in top 20"
        AmazonRank(product_id=b_any.id, date=TODAY, category_key="cat_b", list_name="bestsellers", rank=1),
    ])
    session.flush()
    alerts = detect_alerts(session, TODAY, AlertsConfig(), NOW)
    assert [(a.kind, a.subject_id) for a in alerts] == [("amazon", a_new.id)]
