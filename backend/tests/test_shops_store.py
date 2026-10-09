from datetime import date, datetime

from sqlalchemy import select

from app.connectors.base import ShopInfo
from app.models import Product, Shop, ShopSnapshot
from app.pipeline.store import upsert_product, upsert_shop
from tests.fakes import make_product

D1, D2 = date(2026, 10, 6), date(2026, 10, 7)


def shop_info(**overrides) -> ShopInfo:
    values = dict(
        shop_id=42, name="NurseLifeCo", url="https://www.etsy.com/shop/NurseLifeCo",
        icon_url="https://img/icon.jpg", opened_at=datetime(2021, 1, 1), sold_count=1000,
        favorers=200, listing_count=50, review_average=4.9, review_count=120,
    )
    values.update(overrides)
    return ShopInfo(**values)


def test_upsert_shop_creates_shop_and_snapshot(session):
    shop = upsert_shop(session, shop_info(), D1)
    session.commit()

    assert shop.id == 42
    row = session.get(Shop, 42)
    assert (row.name, row.url, row.icon_url, row.opened_at) == (
        "NurseLifeCo", "https://www.etsy.com/shop/NurseLifeCo", "https://img/icon.jpg", datetime(2021, 1, 1)
    )
    assert (row.first_seen, row.last_seen, row.watched_at) == (D1, D1, None)
    snap = session.scalar(select(ShopSnapshot))
    assert (snap.shop_id, snap.date, snap.sold_count, snap.favorers, snap.listing_count) == (42, D1, 1000, 200, 50)
    assert (snap.review_average, snap.review_count) == (4.9, 120)


def test_upsert_shop_twice_same_day_overwrites_snapshot(session):
    upsert_shop(session, shop_info(sold_count=1000), D1)
    upsert_shop(session, shop_info(sold_count=1012, name="Renamed"), D1)
    session.commit()

    snaps = session.scalars(select(ShopSnapshot)).all()
    assert [(s.date, s.sold_count) for s in snaps] == [(D1, 1012)]
    assert session.get(Shop, 42).name == "Renamed"


def test_upsert_shop_next_day_adds_snapshot_and_keeps_first_seen(session):
    upsert_shop(session, shop_info(sold_count=1000), D1)
    upsert_shop(session, shop_info(sold_count=1030), D2)
    session.commit()

    snaps = session.scalars(select(ShopSnapshot).order_by(ShopSnapshot.date)).all()
    assert [(s.date, s.sold_count) for s in snaps] == [(D1, 1000), (D2, 1030)]
    row = session.get(Shop, 42)
    assert (row.first_seen, row.last_seen) == (D1, D2)


def test_upsert_shop_keeps_watched_at(session):
    upsert_shop(session, shop_info(), D1)
    session.get(Shop, 42).watched_at = datetime(2026, 10, 6, 12)
    upsert_shop(session, shop_info(), D2)
    session.commit()

    assert session.get(Shop, 42).watched_at == datetime(2026, 10, 6, 12)


def test_upsert_product_links_shop(session):
    product = upsert_product(session, make_product(shop=shop_info()), D1)
    session.commit()

    assert product.shop_id == 42
    assert session.get(Shop, 42) is not None
    assert len(session.scalars(select(ShopSnapshot)).all()) == 1


def test_upsert_product_without_shop_leaves_shop_id_none(session):
    product = upsert_product(session, make_product(), D1)
    session.commit()

    assert product.shop_id is None
    assert session.scalars(select(Shop)).all() == []
    assert session.scalar(select(Product)).shop_id is None


def test_same_day_rescan_keeps_earlier_non_none_snapshot_fields(session):
    upsert_shop(session, shop_info(sold_count=1000, favorers=200, review_average=4.9), D1)
    upsert_shop(session, shop_info(sold_count=1005, favorers=None, review_average=None), D1)
    session.commit()
    snap = session.scalar(select(ShopSnapshot))
    assert (snap.sold_count, snap.favorers, snap.review_average) == (1005, 200, 4.9)


def test_many_products_of_one_shop_upsert_shop_once(session):
    import re

    from sqlalchemy import event

    info = shop_info()
    upsert_product(session, make_product(external_id="p0", shop=info), D1)
    statements: list[str] = []

    def grab(conn, cur, stmt, *a):
        statements.append(stmt)

    event.listen(session.get_bind(), "before_cursor_execute", grab)
    for i in range(1, 5):
        upsert_product(session, make_product(external_id=f"p{i}", shop=info), D1)
    event.remove(session.get_bind(), "before_cursor_execute", grab)
    assert len(session.scalars(select(ShopSnapshot)).all()) == 1
    assert not [s for s in statements if re.search(r"\bshops\b|shop_snapshots", s)]


def test_memo_does_not_hide_changed_values(session):
    upsert_shop(session, shop_info(sold_count=1000), D1)
    upsert_shop(session, shop_info(sold_count=1012), D1)
    session.commit()
    assert session.scalar(select(ShopSnapshot)).sold_count == 1012
