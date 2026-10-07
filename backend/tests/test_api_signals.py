from datetime import date, datetime

import pytest

from app.keywords import get_or_create_keyword
from app.models import ListingSignal, Product

D = date(2026, 10, 5)
OLD = date(2026, 10, 4)


def _product(session, n, tags=None, listed_at=None):
    p = Product(
        source="etsy", external_id=str(n), title=f"t{n}", url=f"https://e/{n}",
        shop_name="shop", price=20.0, currency="USD", product_type="tshirt",
        listed_at=listed_at, shop_sold_count=5, tags=tags,
    )
    session.add(p)
    session.flush()
    return p


def _signal(session, p, status, updated_on=D, **kw):
    kw.setdefault("age_days", 5)
    session.add(ListingSignal(
        product_id=p.id, discovered_on=OLD, discovery_query="q", status=status,
        updated_on=updated_on, **kw,
    ))


@pytest.fixture
def data(session):
    kw = get_or_create_keyword(session, "vintage sasquatch")
    a = _product(session, 1, ["vintage sasquatch", "other"], datetime(2026, 10, 1))
    b = _product(session, 2, None, datetime(2026, 10, 3))
    c = _product(session, 3, None, datetime(2026, 9, 1))
    g = _product(session, 4, None, datetime(2026, 10, 2))
    _signal(session, a, "super_breakout", age_days=4, delta_saves=9.0, dsr=0.1, delta_views=1.0)
    _signal(session, b, "normal", age_days=2, delta_saves=None, dsr=0.5, delta_views=5.0)
    _signal(session, c, "graduated", age_days=30, delta_saves=3.0, dsr=None, delta_views=None)
    _signal(session, g, "gone", age_days=3, delta_saves=1.0)
    _signal(session, _product(session, 5), "steady_grower", updated_on=OLD)
    session.commit()
    return kw.id


def ids(r):
    return [i["product_id"] for i in r.json()["items"]]


def test_empty(client):
    r = client.get("/api/signals")
    assert r.json() == {"updated_on": None, "counts": {}, "total": 0, "items": []}


def test_default_signals_and_counts(client, data):
    body = client.get("/api/signals").json()
    assert body["updated_on"] == "2026-10-05"
    assert [i["product_id"] for i in body["items"]] == [1, 3]
    assert body["total"] == 2
    assert body["counts"] == {"super_breakout": 1, "normal": 1, "graduated": 1}
    first = body["items"][0]
    assert first["tags"] == [
        {"tag": "vintage sasquatch", "keyword_id": data},
        {"tag": "other", "keyword_id": None},
    ]
    assert first["status"] == "super_breakout"


def test_all_excludes_gone(client, data):
    r = client.get("/api/signals?status=all")
    assert sorted(ids(r)) == [1, 2, 3]
    assert r.json()["total"] == 3


def test_status_gone_and_single(client, data):
    assert ids(client.get("/api/signals?status=gone")) == [4]
    assert ids(client.get("/api/signals?status=normal")) == [2]


def test_sort(client, data):
    assert ids(client.get("/api/signals?status=all&sort=newest")) == [2, 1, 3]
    assert ids(client.get("/api/signals?status=all&sort=delta_saves")) == [1, 3, 2]
    assert ids(client.get("/api/signals?status=all&sort=dsr")) == [2, 1, 3]
    assert ids(client.get("/api/signals?status=all&sort=delta_views")) == [2, 1, 3]


def test_max_age_limit_offset(client, data):
    assert ids(client.get("/api/signals?status=all&max_age=3")) == [2]
    r = client.get("/api/signals?status=all&limit=1&offset=1")
    assert ids(r) == [3] and r.json()["total"] == 3


def test_bad_params(client, data):
    assert client.get("/api/signals?status=bogus").status_code == 422
    assert client.get("/api/signals?sort=bogus").status_code == 422
    assert client.get("/api/signals?max_age=0").status_code == 422


def test_signals_keyword_filter(client, session):
    a = _product(session, 11)
    b = _product(session, 12)
    a.title = "Pickleball Queen Tee"
    b.title = "Dog Tee"
    _signal(session, a, "steady_grower")
    _signal(session, b, "steady_grower")
    _signal(session, _product(session, 13), "normal")  # title t13: excluded from counts by keyword
    session.commit()
    r = client.get("/api/signals", params={"keyword": "Pickleball", "status": "all"})
    body = r.json()
    assert [i["title"] for i in body["items"]] == ["Pickleball Queen Tee"]
    assert body["total"] == 1
    assert body["counts"] == {"steady_grower": 1}
    unfiltered = client.get("/api/signals", params={"status": "all"}).json()
    assert unfiltered["total"] == 3
