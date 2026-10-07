from datetime import date

import pytest

from app.analysis.amazon import load_amazon_config
from app.models import AmazonRank, Product, ProductSnapshot

D1 = date(2026, 10, 4)
D2 = date(2026, 10, 5)
CAT = load_amazon_config().categories[0]


def _product(session, asin, licensed=False, rating=4.5, reviews=10):
    p = Product(
        source="amazon", external_id=asin, title=f"Title {asin}", url=f"https://amazon.com/dp/{asin}",
        image_url=f"https://img/{asin}.jpg", product_type=CAT.product_type, licensed=licensed,
    )
    session.add(p)
    session.flush()
    session.add(ProductSnapshot(product_id=p.id, date=D1, reviews=1, rating=3.0))
    session.add(ProductSnapshot(product_id=p.id, date=D2, reviews=reviews, rating=rating))
    return p


def _rank(session, product, day, rank, list_name="bestsellers", cat=None):
    session.add(AmazonRank(
        product_id=product.id, date=day, category_key=cat or CAT.key, list_name=list_name, rank=rank
    ))


@pytest.fixture
def data(session):
    a = _product(session, "A1")
    b = _product(session, "B2", licensed=True)
    c = _product(session, "C3")
    _rank(session, a, D1, 3)
    _rank(session, a, D2, 1)
    _rank(session, b, D1, 1)
    _rank(session, b, D2, 2)
    _rank(session, c, D2, 3)
    _rank(session, c, D2, 1, list_name="new_releases")
    session.commit()


def test_empty(client):
    body = client.get("/api/amazon").json()
    assert body["date"] is None and body["items"] == []
    assert body["category"] == CAT.key and body["list"] == "bestsellers"
    assert {"key": CAT.key, "product_type": CAT.product_type} in body["categories"]


def test_rank_change_and_new_entry(client, data):
    body = client.get(f"/api/amazon?category={CAT.key}").json()
    assert body["date"] == "2026-10-05"
    a, b, c = body["items"]
    assert [i["asin"] for i in body["items"]] == ["A1", "B2", "C3"]
    assert (a["rank"], a["prev_rank"], a["rank_change"], a["is_new_entry"]) == (1, 3, 2, False)
    assert (b["prev_rank"], b["rank_change"]) == (1, -1)
    assert (c["prev_rank"], c["rank_change"], c["is_new_entry"]) == (None, None, True)
    assert a["rating"] == 4.5 and a["reviews"] == 10
    assert a["licensed"] is False and b["licensed"] is True
    assert a["title"] == "Title A1" and a["image_url"] and a["url"]


def test_other_list(client, data):
    items = client.get("/api/amazon?list=new_releases").json()["items"]
    assert [i["asin"] for i in items] == ["C3"]


def test_hide_licensed(client, data):
    items = client.get("/api/amazon?hide_licensed=true").json()["items"]
    assert [i["asin"] for i in items] == ["A1", "C3"]


def test_unknown_category_or_list(client):
    assert client.get("/api/amazon?category=nope").status_code == 422
    assert client.get("/api/amazon?list=nope").status_code == 422


def test_first_day_has_no_new_entries(client, session):
    a = _product(session, "F1")
    b = _product(session, "F2")
    _rank(session, a, D2, 1)
    _rank(session, b, D2, 2)
    session.commit()
    items = client.get("/api/amazon").json()["items"]
    assert [i["is_new_entry"] for i in items] == [False, False]


def test_old_history_outside_window_means_no_new_entries(client, session):
    a = _product(session, "G1")
    _rank(session, a, date(2026, 9, 1), 5)
    _rank(session, a, D2, 1)
    session.commit()
    (item,) = client.get("/api/amazon").json()["items"]
    assert item["is_new_entry"] is False and item["prev_rank"] == 5
