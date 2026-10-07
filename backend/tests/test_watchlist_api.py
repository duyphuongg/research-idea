from datetime import date

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, KeywordScore, ListingSignal, Product, Seed

D = date(2026, 10, 8)


def test_watchlist_card(client, session):
    session.add(Seed(keyword="pickleball"))
    kw = get_or_create_keyword(session, "pickleball")
    kids = [get_or_create_keyword(session, f"pickleball {w}", origin="discovered", has_parent=True)
            for w in ("queen", "dad", "mom", "coach")]
    for i, k in enumerate(kids):
        session.add(KeywordRelation(parent_id=kw.id, child_id=k.id, source="etsy", last_seen=D))
        session.add(KeywordScore(keyword_id=k.id, score=50 + i, date=D))
    session.add(KeywordScore(keyword_id=kw.id, score=61, growth=0.3, date=D))
    for i, status in enumerate(["super_breakout", "steady_grower", "steady_grower", "calibrating"]):
        p = Product(source="etsy", external_id=f"p{i}", title=f"Pickleball tee {i}", url="u",
                    image_url=f"https://img/{i}.jpg", product_type="tshirt")
        session.add(p)
        session.flush()
        session.add(ListingSignal(product_id=p.id, discovered_on=D, discovery_query="graphic tee",
                                  status=status, delta_saves=i, updated_on=D))
    session.commit()

    page = client.get("/api/watchlist").json()
    assert page["date"] == "2026-10-08"
    item = page["items"][0]
    assert item["keyword"] == "pickleball" and item["score"] == 61 and item["growth"] == 0.3
    assert item["children_total"] == 4
    assert [c["keyword"] for c in item["children"]] == ["pickleball coach", "pickleball mom", "pickleball dad"]
    assert item["listings"] == {"super_breakout": 1, "steady_grower": 2}
    assert item["thumbnails"][0]["status"] == "super_breakout" and len(item["thumbnails"]) == 3
    assert item["alerts_7d"] == 0


def test_watchlist_empty(client):
    assert client.get("/api/watchlist").json() == {"date": None, "items": []}
