from datetime import date, datetime, timedelta

import pytest

from app.models import Product, ProductSnapshot, Shop, ShopSnapshot

L = date(2026, 10, 9)


def d(days_ago: int) -> date:
    return L - timedelta(days=days_ago)


def add_shop(session, shop_id, snaps, opened=None, watched=False, last_seen=L):
    """snaps: list of (days_ago, sold, listings, rating)."""
    session.add(Shop(
        id=shop_id, name=f"Shop{shop_id}", url=f"https://etsy.com/shop/{shop_id}", icon_url=None,
        opened_at=opened, first_seen=d(40), last_seen=last_seen,
        watched_at=datetime(2026, 10, 1) if watched else None,
    ))
    for ago, sold, listings, rating in snaps:
        session.add(ShopSnapshot(shop_id=shop_id, date=d(ago), sold_count=sold, favorers=sold // 10,
                                 listing_count=listings, review_average=rating, review_count=5))
    session.flush()


@pytest.fixture
def shops(session):
    # id: 7d sales, sold, listings, spl, opened, rating
    add_shop(session, 1, [(30, 40000, 100, 4.9), (7, 50000, 100, 4.9), (0, 60000, 100, 4.9)],
             opened=datetime(2026, 2, 1), watched=True)          # 7d 10000, spl 600
    add_shop(session, 2, [(7, 2000, 500, 4.6), (0, 2100, 500, 4.6)],
             opened=datetime(2025, 5, 1))                        # 7d 100, spl 4.2
    add_shop(session, 3, [(0, 12000, 2000, 4.85)], opened=datetime(2020, 1, 1))  # 7d None, spl 6
    add_shop(session, 4, [(2, 900, 30, None), (0, 990, 30, None)], last_seen=d(1))  # 7d 90 (2 days)
    session.add(Product(source="etsy", external_id="a", title="Funny Nurse Shirt", url="https://e/a",
                        product_type="tshirt", shop_id=2, listed_at=datetime(2026, 9, 1)))
    session.add(Product(source="etsy", external_id="b", title="Nursery Tee", url="https://e/b",
                        product_type="tshirt", shop_id=3))
    session.commit()


def ids(resp):
    assert resp.status_code == 200, resp.text
    return [item["id"] for item in resp.json()["items"]]


def test_list_default_sort_sales_7d_none_last(client, shops):
    resp = client.get("/api/shops")
    body = resp.json()
    assert body["total"] == 4
    assert body["latest_date"] == "2026-10-09"
    assert ids(resp) == [1, 2, 4, 3]
    first = body["items"][0]
    assert first["sales_7d"] == {"value": 10000, "days": 7}
    assert first["sales_30d"] == {"value": 20000, "days": 30}
    assert first["favorers_7d"] == {"value": 1000, "days": 7}
    assert first["opened_year"] == 2026
    assert first["watched"] is True
    assert first["sales_per_listing"] == pytest.approx(600)
    assert first["review_count"] == 5
    assert first["last_seen"] == "2026-10-09"
    assert body["items"][2]["sales_7d"] == {"value": 90, "days": 2}
    assert body["items"][3]["sales_7d"] is None


def test_list_sort_asc_keeps_none_last(client, shops):
    assert ids(client.get("/api/shops?order=asc")) == [4, 2, 1, 3]
    assert ids(client.get("/api/shops?sort=review_average")) == [1, 3, 2, 4]
    assert ids(client.get("/api/shops?sort=review_average&order=asc")) == [2, 3, 1, 4]
    assert ids(client.get("/api/shops?sort=opened_at")) == [1, 2, 3, 4]
    assert ids(client.get("/api/shops?sort=sold_count&order=asc")) == [4, 2, 3, 1]
    assert ids(client.get("/api/shops?sort=last_seen&order=asc"))[0] == 4


def test_list_filters(client, shops):
    assert ids(client.get("/api/shops?min_sales=5000")) == [1, 3]
    assert ids(client.get("/api/shops?listings=lt200")) == [1, 4]
    assert ids(client.get("/api/shops?listings=200_1000")) == [2]
    assert ids(client.get("/api/shops?listings=gt1000")) == [3]
    assert ids(client.get("/api/shops?min_spl=30")) == [1, 4]
    assert ids(client.get("/api/shops?min_spl=50")) == [1]
    assert ids(client.get("/api/shops?opened=2026")) == [1]
    assert ids(client.get("/api/shops?opened=2025plus")) == [1, 2]
    assert ids(client.get("/api/shops?opened=before2024")) == [3]
    assert ids(client.get("/api/shops?min_rating=4.8")) == [1, 3]
    assert ids(client.get("/api/shops?watched=true")) == [1]
    assert ids(client.get("/api/shops?watched=false")) == [2, 4, 3]


def test_list_q_whole_word(client, shops):
    assert ids(client.get("/api/shops?q=nurse")) == [2]
    assert ids(client.get("/api/shops?q=%20")) == [1, 2, 4, 3]


def test_list_pagination_and_validation(client, shops):
    resp = client.get("/api/shops?limit=2&offset=1")
    assert resp.json()["total"] == 4
    assert ids(resp) == [2, 4]
    assert client.get("/api/shops?sort=bogus").status_code == 422
    assert client.get("/api/shops?listings=bogus").status_code == 422


def test_list_empty(client):
    body = client.get("/api/shops").json()
    assert body == {"total": 0, "latest_date": None, "items": []}


def test_detail(client, session, shops):
    for i in range(30):
        session.add(Product(source="etsy", external_id=f"x{i}", title=f"Teacher Tee {i}",
                            url=f"https://e/x{i}", product_type="tshirt", shop_id=1,
                            listed_at=datetime(2026, 1, 1) + timedelta(days=i)))
    session.flush()
    session.add(ProductSnapshot(product_id=session.query(Product).filter_by(external_id="x29").one().id,
                                date=L, favorites=7))
    session.add(ShopSnapshot(shop_id=1, date=d(120), sold_count=1, favorers=0, listing_count=1))
    session.commit()

    body = client.get("/api/shops/1").json()
    assert body["id"] == 1 and body["name"] == "Shop1"
    assert [p["date"] for p in body["series"]] == [str(d(30)), str(d(7)), str(L)]
    assert body["series"][-1] == {"date": str(L), "sold_count": 60000, "favorers": 6000}
    assert len(body["products"]) == 24
    newest = body["products"][0]
    assert newest["title"] == "Teacher Tee 29"
    assert newest["favorites"] == 7
    assert {"id", "title", "url", "image_url", "price", "currency", "product_type", "hot", "keywords"} <= set(newest)


def test_detail_404(client, shops):
    assert client.get("/api/shops/999").status_code == 404


def test_watch_toggle(client, session, shops):
    resp = client.post("/api/shops/2/watch")
    assert resp.status_code == 200
    assert resp.json()["watched"] is True
    assert resp.json()["sales_7d"] == {"value": 100, "days": 7}
    session.expire_all()
    assert session.get(Shop, 2).watched_at is not None

    resp = client.delete("/api/shops/2/watch")
    assert resp.json()["watched"] is False
    session.expire_all()
    assert session.get(Shop, 2).watched_at is None

    assert client.post("/api/shops/999/watch").status_code == 404
    assert client.delete("/api/shops/999/watch").status_code == 404
