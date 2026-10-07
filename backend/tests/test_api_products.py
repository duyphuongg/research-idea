from datetime import date, datetime

import pytest

from app.keywords import get_or_create_keyword
from app.models import Product, ProductKeyword, ProductSnapshot


def add_product(session, external_id, product_type, listed_at, snapshots, keyword=None, price=20.0):
    p = Product(
        source="etsy",
        external_id=external_id,
        title=f"Product {external_id}",
        url=f"https://etsy.com/{external_id}",
        product_type=product_type,
        listed_at=listed_at,
        price=price,
        currency="USD",
    )
    session.add(p)
    session.flush()
    for d, fav in snapshots:
        session.add(ProductSnapshot(product_id=p.id, date=d, favorites=fav))
    if keyword:
        kw = get_or_create_keyword(session, keyword)
        session.add(ProductKeyword(product_id=p.id, keyword_id=kw.id, rank=1, last_seen=snapshots[-1][0]))
    return p


@pytest.fixture
def catalog(session):
    a = add_product(
        session, "A", "tshirt", datetime(2026, 9, 13),
        [(date(2026, 9, 20), 100), (date(2026, 9, 27), 170)], keyword="nurse", price=25.0,
    )
    b = add_product(
        session, "B", "tshirt", datetime(2025, 1, 1),
        [(date(2026, 9, 20), 500), (date(2026, 9, 27), 510)], price=15.0,
    )
    c = add_product(session, "C", "hoodie", datetime(2026, 9, 26), [(date(2026, 9, 27), 3)], price=40.0)
    session.commit()
    return {"A": a.id, "B": b.id, "C": c.id}


def ids(resp):
    return [item["id"] for item in resp.json()["items"]]


def test_default_sort_is_velocity_with_hot_flag(client, catalog):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert ids(resp) == [catalog["A"], catalog["B"], catalog["C"]]
    a, b, c = body["items"]
    assert a["hot"] is True and b["hot"] is False and c["hot"] is False
    assert a["delta_7d"] == pytest.approx(70)
    assert a["velocity"] == pytest.approx(35)
    assert a["favorites"] == 170
    assert a["keywords"] == ["nurse"]
    assert c["velocity"] is None


def test_sort_by_reviews_and_price(client, catalog):
    assert ids(client.get("/api/products?sort=reviews")) == [catalog["B"], catalog["A"], catalog["C"]]
    assert ids(client.get("/api/products?sort=price")) == [catalog["B"], catalog["A"], catalog["C"]]
    assert ids(client.get("/api/products?sort=newest")) == [catalog["C"], catalog["A"], catalog["B"]]


def test_filters(client, catalog, session):
    assert ids(client.get("/api/products?type=hoodie")) == [catalog["C"]]
    assert ids(client.get("/api/products?source=amazon")) == []
    kw_id = get_or_create_keyword(session, "nurse").id
    assert ids(client.get(f"/api/products?keyword_id={kw_id}")) == [catalog["A"]]


def test_pagination(client, catalog):
    resp = client.get("/api/products?limit=1&offset=1")
    assert resp.json()["total"] == 3
    assert ids(resp) == [catalog["B"]]


def test_invalid_sort_rejected(client):
    assert client.get("/api/products?sort=bogus").status_code == 422


def test_ties_are_ordered_by_id(client, session):
    """Test that products with same velocity (all None) are ordered by id"""
    # Insert several products with no snapshots (velocity None for all)
    products = []
    for i in range(4):
        p = add_product(
            session, f"tie_{i}", "tshirt", datetime(2026, 9, 27),
            [(date(2026, 9, 27), 1)],  # At least one snapshot, no keyword
        )
        products.append(p)
    session.commit()

    # All products have velocity=None (no change over time)
    # They should be ordered by id
    resp = client.get("/api/products?sort=velocity")
    assert resp.status_code == 200
    returned_ids = ids(resp)
    product_ids = sorted([p.id for p in products])
    assert returned_ids == product_ids

    # Test pagination doesn't duplicate/skip items
    resp1 = client.get("/api/products?sort=velocity&limit=2&offset=0")
    resp2 = client.get("/api/products?sort=velocity&limit=2&offset=2")
    items1 = ids(resp1)
    items2 = ids(resp2)
    assert len(items1) == 2
    assert len(items2) == 2
    assert items1 + items2 == product_ids
    assert len(set(items1) & set(items2)) == 0  # No duplicates


def test_views_shop_sales_and_metric_exposed(client, session):
    p = Product(source="etsy", external_id="V", title="Views", url="u", product_type="tshirt",
                shop_sold_count=777, listed_at=datetime(2026, 9, 1))
    session.add(p)
    session.flush()
    session.add_all([
        ProductSnapshot(product_id=p.id, date=date(2026, 9, 20), favorites=1, views=100),
        ProductSnapshot(product_id=p.id, date=date(2026, 9, 27), favorites=2, views=300),
    ])
    session.commit()

    [item] = client.get("/api/products").json()["items"]
    assert (item["views"], item["shop_sold_count"], item["velocity_metric"]) == (300, 777, "views")
    assert item["delta_7d"] == pytest.approx(200)


def test_listing_signal_only_products_excluded(client, session):
    from app.models import ListingSignal

    only = add_product(session, "S1", "tshirt", datetime(2026, 9, 13), [(date(2026, 9, 27), 5)])
    both = add_product(session, "S2", "tshirt", datetime(2026, 9, 13), [(date(2026, 9, 27), 5)], keyword="nurse")
    plain = add_product(session, "S3", "tshirt", datetime(2026, 9, 13), [(date(2026, 9, 27), 5)])
    session.flush()
    for p in (only, both):
        session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 9, 27), status="normal", discovery_query="q"))
    session.commit()
    got = ids(client.get("/api/products"))
    assert only.id not in got and both.id in got and plain.id in got


def test_licensed_flag_not_hot_and_hide_param(client, session, catalog):
    session.get(Product, catalog["A"]).licensed = True
    session.commit()
    items = {i["id"]: i for i in client.get("/api/products").json()["items"]}
    assert items[catalog["A"]]["licensed"] is True
    assert items[catalog["A"]]["hot"] is False
    assert items[catalog["B"]]["licensed"] is None
    resp = client.get("/api/products?hide_licensed=true")
    assert catalog["A"] not in ids(resp)
    assert resp.json()["total"] == 2
    assert catalog["A"] in ids(client.get("/api/products?hide_licensed=false"))
