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


def test_detects_niche_and_listing_but_never_amazon(session):
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
    assert got == sorted([("niche", child.id), ("listing", lp.id)])
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


async def test_run_scan_survives_alert_failure(session_factory, monkeypatch):
    from app.pipeline import scan as scan_mod
    from tests.fakes import FakeConnector

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(scan_mod, "detect_alerts", boom)
    run_ids = await scan_mod.run_scan(session_factory, [FakeConnector()])
    assert len(run_ids) == 1


def _watched_shop(session, sid, snaps, watched=True):
    from datetime import timedelta

    from app.models import Shop, ShopSnapshot

    session.add(Shop(id=sid, name=f"Shop{sid}", url=f"https://www.etsy.com/shop/S{sid}",
                     icon_url=f"https://img/s{sid}.jpg", first_seen=TODAY, last_seen=TODAY,
                     watched_at=NOW if watched else None))
    for ago, sold in snaps:
        session.add(ShopSnapshot(shop_id=sid, date=TODAY - timedelta(days=ago), sold_count=sold))
    session.flush()


def test_shop_alerts_only_for_watched_shops(session):
    _watched_shop(session, 1, [(14, 0), (7, 20), (0, 60)])         # +40 vs +20 last week -> alert
    _watched_shop(session, 2, [(14, 0), (7, 30), (0, 70)])         # +40 vs +30: not 1.5x
    _watched_shop(session, 3, [(7, 0), (0, 35)])                   # no previous week: minimum only
    _watched_shop(session, 4, [(3, 0), (0, 100)])                  # < 7 days of history
    _watched_shop(session, 5, [(7, 0), (0, 100)], watched=False)   # not watched
    _watched_shop(session, 6, [])                                  # no snapshots
    alerts = detect_alerts(session, TODAY, AlertsConfig(), NOW)
    assert sorted(a.subject_id for a in alerts if a.kind == "shop") == [1, 3]
    one = next(a for a in alerts if a.subject_id == 1)
    assert (one.title, one.reason, one.link, one.image_url, one.external_url, one.watch_keyword, one.priority) == (
        "Shop1", "+40 đơn/7 ngày (tuần trước +20)", "/shops/1", "https://img/s1.jpg",
        "https://www.etsy.com/shop/S1", None, 40)
    assert detect_alerts(session, TODAY, AlertsConfig(), NOW) == []  # cooldown


def test_listed_or_skipped_subjects_are_not_alerted(session):
    from app.models import WorkItem

    session.add(Seed(keyword="game day"))
    seed_kw = get_or_create_keyword(session, "game day")
    child = get_or_create_keyword(session, "game day vibes", origin="discovered", has_parent=True)
    session.add(KeywordRelation(parent_id=seed_kw.id, child_id=child.id, source="etsy", last_seen=TODAY))
    session.add(KeywordScore(keyword_id=child.id, score=70, growth=0.5, date=TODAY))
    done = _product(session, "d1", "Anything")
    idea = _product(session, "d2", "Other")
    for p in (done, idea):
        session.add(ListingSignal(product_id=p.id, discovered_on=TODAY, discovery_query="shirt",
                                  status="super_breakout", delta_saves=20, dsr=0.3, updated_on=TODAY))
    session.add_all([
        WorkItem(subject_kind="keyword", subject_id=child.id, status="listed"),
        WorkItem(subject_kind="product", subject_id=done.id, status="skipped"),
        WorkItem(subject_kind="product", subject_id=idea.id, status="idea"),
    ])
    session.flush()

    alerts = detect_alerts(session, TODAY, AlertsConfig(), NOW)
    assert [(a.kind, a.subject_id) for a in alerts] == [("listing", idea.id)]


def _nfl_week(session, week, game_date, players):
    from app.models import NflPerformance, NflPlayerDemand

    for aid, points in players:
        session.add(NflPerformance(season=2026, season_type=2, week=week, event_id=f"{week}-{aid}", game="A at B",
                                   game_date=game_date, athlete_id=aid, name=f"P{aid}", position="WR", team="DAL",
                                   category="receivingYards", stat_line=f"{points:.0f} YDS", points=points))
        session.add(NflPlayerDemand(athlete_id=aid, date=game_date.date(), etsy_listings=9999, merch_suggestions=10))
    session.flush()


def test_nfl_alert_once_per_week_and_only_for_recent_weeks(session):
    cfg = AlertsConfig(nfl_min_potential=85, nfl_max_per_week=3)
    players = [(str(i), float(i)) for i in range(1, 13)]  # 12 games: a full week
    _nfl_week(session, 4, datetime(2026, 10, 6, 1), players)

    first = detect_alerts(session, TODAY, cfg, NOW)
    nfl = [a for a in first if a.kind == "nfl"]
    assert [a.subject_id for a in nfl] == [12, 11, 10]
    assert nfl[0].reason.startswith("Tuần 4 · 12 YDS · tiềm năng 100"), nfl[0].reason
    assert nfl[0].link == "/nfl"
    later = datetime(2026, 10, 9, 13)
    assert [a for a in detect_alerts(session, TODAY, cfg, later) if a.kind == "nfl"] == []  # same week

    _nfl_week(session, 5, datetime(2026, 10, 13, 1), players)  # next week: same players again
    week5 = [a for a in detect_alerts(session, TODAY, cfg, datetime(2026, 10, 13, 13)) if a.kind == "nfl"]
    assert [a.subject_id for a in week5] == [12, 11, 10]

    stale = datetime(2026, 10, 30)
    assert [a for a in detect_alerts(session, TODAY, cfg, stale) if a.kind == "nfl"] == []


def test_nfl_alerts_ring_the_bell():
    from app.notify.telegram import _high_priority

    assert _high_priority(Alert(kind="nfl", level=1)) is True
