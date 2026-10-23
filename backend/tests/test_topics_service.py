from datetime import date, timedelta

import pytest

from app.analysis.topics import TopicsConfig
from app.models import Alert, Product, ProductSnapshot, TopicSnapshot
from app.services.alerts import detect_alerts
from app.services.topics import compute_topics, latest_topics, listing_gains, topic_subject_id

REF = date(2026, 10, 23)
CFG = TopicsConfig(min_listings=3, min_shops=2, prior_weight=2, generic_words=frozenset({"shirt"}))


def add(session, n, tags, daily_gain, days=15, shop=None, title=None, licensed=False, end=REF):
    p = Product(source="etsy", external_id=str(n), title=title or f"Listing {n}", url=f"https://e/{n}",
                image_url=f"https://img/{n}", product_type="tshirt", tags=tags, shop_id=shop or n, licensed=licensed)
    session.add(p)
    session.flush()
    for i in range(days):
        d = end - timedelta(days=days - 1 - i)
        session.add(ProductSnapshot(product_id=p.id, date=d, favorites=int(daily_gain * i)))
    return p


@pytest.fixture
def catalog(session):
    for n in range(1, 6):
        add(session, n, ["Gingham Applique Shirt"], 3)  # 21 saves / week, every shop different
    for n in range(10, 20):
        add(session, n, [f"misc {n}"], 0.2)
    add(session, 30, ["gingham applique"], 50, licensed=True)  # never counted
    add(session, 31, ["gingham applique"], 50, title="Gingham Applique SVG PNG digital download")
    session.commit()


def test_listing_gains_skip_licensed_digital_and_stale(session, catalog):
    add(session, 40, ["gingham applique"], 5, days=5, end=REF - timedelta(days=5))  # no longer refreshed
    session.commit()
    gains = {g.product_id: g for g in listing_gains(session)}
    assert len(gains) == 15
    g = gains[session.query(Product.id).filter_by(external_id="1").scalar()]
    assert g.gain == pytest.approx(21) and g.prev_gain == pytest.approx(21)


def test_compute_and_read_back(session, catalog):
    rows = compute_topics(session, REF, CFG)
    session.commit()
    assert rows[0].key == "gingham applique" and rows[0].rank == 1
    assert rows[0].listings == 5 and rows[0].ip_level == "green"
    compute_topics(session, REF, CFG)  # same-day rerun replaces
    session.commit()
    assert session.query(TopicSnapshot).filter_by(key="gingham applique").count() == 1

    page = latest_topics(session, CFG)
    top = page["items"][0]
    assert page["date"] == REF
    assert top["new"] is False  # first day ever: nothing to compare against
    assert top["growth"] == pytest.approx(0)
    assert len(top["products"]) == 4 and top["products"][0]["image_url"].startswith("https://img/")
    assert [p["date"] for p in top["series"]] == [REF]


def test_new_flag_and_alert(session, catalog):
    session.add(TopicSnapshot(date=REF - timedelta(days=1), key="old niche", rank=1, aliases=[], listings=5,
                              shops=5, rising=5, gain_7d=10, prev_gain_7d=None, score=2.0, product_ids=[],
                              ip_level="green"))
    compute_topics(session, REF, CFG)
    session.commit()
    top = latest_topics(session, CFG)["items"][0]
    assert top["key"] == "gingham applique" and top["new"] is True

    alerts = [a for a in detect_alerts(session, REF) if a.kind == "topic"]
    assert [a.title for a in alerts] == ["gingham applique"]
    assert alerts[0].subject_id == topic_subject_id("gingham applique")
    assert alerts[0].link == "/topics?key=gingham+applique"
    assert alerts[0].image_url.startswith("https://img/")
    session.commit()
    assert not [a for a in detect_alerts(session, REF) if a.kind == "topic"]  # cooldown
    assert session.query(Alert).filter_by(kind="topic").count() == 1


def test_api(client, session, catalog, monkeypatch):
    import app.services.topics as topics_mod

    monkeypatch.setattr(topics_mod, "load_topics_config", lambda: CFG)
    assert client.get("/api/topics").json() == {"date": None, "total": 0, "items": []}
    compute_topics(session, REF, CFG)
    session.commit()
    body = client.get("/api/topics?sort=growth").json()
    assert body["date"] == "2026-10-23" and body["items"][0]["key"] == "gingham applique"
    assert client.get("/api/topics?new_only=true").json()["total"] == 0
