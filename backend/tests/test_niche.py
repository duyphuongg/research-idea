from datetime import date

from app.keywords import get_or_create_keyword
from app.models import ListingSignal, Product, ProductKeyword, ProductSnapshot, TrendSignal
from app.services.niche import competition_level, generate_tags, niche_report, percentile

TODAY = date(2026, 10, 9)


def _p(session, ext, title, tags, price=20.0, ptype="tshirt", breakout=False, seen=TODAY):
    p = Product(source="etsy", external_id=ext, title=title, url=f"https://x/{ext}", product_type=ptype,
                price=price, tags=tags)
    session.add(p)
    session.flush()
    session.add(ProductSnapshot(product_id=p.id, date=seen, price=price))
    if breakout:
        session.add(ListingSignal(product_id=p.id, discovered_on=TODAY, discovery_query="x shirt",
                                  status="super_breakout", updated_on=TODAY))
    return p


def test_percentile():
    assert percentile([10, 20, 30, 40], 0.5) == 25
    assert percentile([10, 20, 30, 40], 0.25) == 17.5
    assert percentile([7], 0.75) == 7


def test_competition_level():
    assert competition_level(None) is None
    assert competition_level(9_999) == "low"
    assert competition_level(10_000) == "medium"
    assert competition_level(50_000) == "high"


def test_generate_tags_dedupes_limits_and_puts_keyword_first():
    rows = [
        {"tag": "hockey moms", "share": 0.9, "breakout_share": 0.9},
        {"tag": "hockey mom shirt for game day", "share": 0.8, "breakout_share": 0.8},  # > 20 chars
        {"tag": "hockey mom", "share": 0.5, "breakout_share": 0.0},
        {"tag": "ice hockey", "share": 0.4, "breakout_share": 0.5},
        *({"tag": f"tag {i}", "share": 0.1, "breakout_share": 0.0} for i in range(20)),
    ]
    tags, phrases = generate_tags("hockey mom", rows)
    assert tags[0] == "hockey mom" and "hockey moms" not in tags
    assert "ice hockey" in tags and len(tags) == 13 and all(len(t) <= 20 for t in tags)
    assert phrases[0] == "hockey moms" and "hockey mom shirt for game day" in phrases
    assert all(" " in p for p in phrases) and len(phrases) <= 6


def test_niche_report(session):
    kw = get_or_create_keyword(session, "hockey mom")
    a = _p(session, "1", "Hockey Mom Shirt", ["hockey mom", "ice hockey", "mom gift"], 20, breakout=True)
    _p(session, "2", "Hockey-Moms Tee", ["hockey mom", "mom gift"], 30)
    _p(session, "3", "Proud Hockey Mom Hoodie", ["hockey mom"], 50, ptype="hoodie")
    _p(session, "4", "Hockey Momentum Tee", ["x"], 10)  # not a whole word
    _p(session, "5", "Hockey Mom Old Tee", ["old"], 10, seen=date(2026, 8, 1))  # stale
    linked = _p(session, "6", "Game Day Tee", ["ice hockey"], 40)  # linked via product_keywords
    session.add(ProductKeyword(product_id=linked.id, keyword_id=kw.id, rank=3, last_seen=TODAY))
    for metric, value in (("listing_count_tshirt", 17445), ("listing_count_hoodie", 3321)):
        session.add(TrendSignal(keyword_id=kw.id, source="etsy", metric=metric, value=value, date=TODAY))
    session.flush()

    r = niche_report(session, "Hockey Mom")
    assert r["keyword"] == "hockey mom" and r["keyword_id"] == kw.id
    assert (r["listings"], r["breakouts"]) == (4, 1)
    assert r["competition"] == {"date": TODAY, "counts": {"tshirt": 17445, "hoodie": 3321}, "level": "medium"}
    prices = {row["product_type"]: row for row in r["prices"]}
    assert prices["tshirt"]["count"] == 3 and prices["tshirt"]["median"] == 30
    assert prices["tshirt"]["breakout_median"] == 20
    assert prices["hoodie"]["breakout_median"] is None
    assert prices["all"]["count"] == 4 and list(prices)[-1] == "all"
    tags = {t["tag"]: t for t in r["tags"]}
    assert r["tags"][0]["tag"] == "hockey mom" and tags["hockey mom"]["listings"] == 3
    assert tags["ice hockey"]["breakouts"] == 1 and tags["ice hockey"]["share"] == 0.5
    assert "x" not in tags and "old" not in tags
    assert r["generated"]["tags"][0] == "hockey mom"

    t = niche_report(session, "hockey mom", product_type="hoodie")
    assert (t["listings"], t["product_type"]) == (1, "hoodie")
    assert [p["product_type"] for p in t["prices"]] == ["hoodie", "all"]

    empty = niche_report(session, "zzz")
    assert empty["keyword_id"] is None and empty["listings"] == 0 and empty["tags"] == []
    assert empty["competition"]["level"] is None and empty["prices"] == []


def test_niche_api(client, session):
    _p(session, "1", "Pickleball Shirt", ["pickleball"], 25)
    session.commit()
    assert client.get("/api/niche?keyword=pickleball").json()["listings"] == 1
    assert client.get("/api/niche?keyword=%20").status_code == 422
    assert client.get("/api/niche?keyword=pickleball&product_type=mug").status_code == 422


def test_graduated_listings_count_as_breakouts(session):
    p = _p(session, "1", "Pickleball Shirt", ["pickleball"], 25)
    session.add(ListingSignal(product_id=p.id, discovered_on=TODAY, discovery_query="x shirt",
                              status="graduated", updated_on=TODAY))
    q = _p(session, "2", "Pickleball Tee", ["pickleball"], 25)
    session.add(ListingSignal(product_id=q.id, discovered_on=TODAY, discovery_query="x shirt",
                              status="normal", updated_on=TODAY))
    session.flush()
    assert niche_report(session, "pickleball")["breakouts"] == 1
