from datetime import date, datetime, timedelta

import pytest

from app.models import Product, Shop, ShopSnapshot
from app.services.shops import Delta, shop_metrics, shops_matching, window_delta

L = date(2026, 10, 9)


def d(days_ago: int) -> date:
    return L - timedelta(days=days_ago)


# --- window_delta ---------------------------------------------------------------------------

def test_window_delta_none_with_fewer_than_two_points():
    assert window_delta([], L, 7) is None
    assert window_delta([(L, 100)], L, 7) is None


def test_window_delta_exact_window():
    points = [(d(10), 50), (d(7), 80), (d(3), 90), (L, 100)]
    assert window_delta(points, L, 7) == Delta(value=20, days=7)


def test_window_delta_uses_newest_snapshot_at_least_window_old():
    points = [(d(20), 10), (d(9), 70), (d(5), 90), (L, 100)]
    assert window_delta(points, L, 7) == Delta(value=30, days=9)


def test_window_delta_short_history_uses_oldest_with_actual_span():
    points = [(d(3), 88), (d(1), 95), (L, 100)]
    assert window_delta(points, L, 7) == Delta(value=12, days=3)
    assert window_delta(points, L, 30) == Delta(value=12, days=3)


def test_window_delta_zero_span_is_none():
    assert window_delta([(L, 100), (L, 100)], L, 7) is None


def test_window_delta_ignores_none_values():
    points = [(d(8), 40), (d(7), None), (d(1), 60), (L, None)]
    # latest usable value is d(1)=60; newest usable value at least 7 days before L is d(8)=40
    assert window_delta(points, L, 7) == Delta(value=20, days=7)
    assert window_delta([(d(7), None), (L, 100)], L, 7) is None


def test_window_delta_ignores_points_after_latest():
    points = [(d(14), 10), (d(7), 30), (L, 100)]
    assert window_delta(points, d(7), 7) == Delta(value=20, days=7)


# --- shop_metrics ---------------------------------------------------------------------------

def add_shop(session, shop_id, snaps, name=None, opened=None, watched=False):
    """snaps: list of (days_ago, sold, favorers, listings)."""
    session.add(Shop(
        id=shop_id, name=name or f"Shop{shop_id}", url=f"https://etsy.com/shop/{shop_id}",
        opened_at=opened, first_seen=d(max((s[0] for s in snaps), default=0)), last_seen=L,
        watched_at=datetime(2026, 10, 1) if watched else None,
    ))
    for ago, sold, fav, listings in snaps:
        session.add(ShopSnapshot(shop_id=shop_id, date=d(ago), sold_count=sold, favorers=fav,
                                 listing_count=listings, review_average=4.8, review_count=10))
    session.flush()


def test_shop_metrics_full_history(session):
    add_shop(session, 1, [(30, 700, 50, 40), (14, 800, 60, 45), (7, 900, 70, 48), (0, 1000, 75, 50)])
    session.commit()

    [m] = shop_metrics(session)
    assert m.shop.id == 1
    assert (m.sold_count, m.listing_count, m.review_average, m.review_count) == (1000, 50, 4.8, 10)
    assert m.sales_7d == Delta(100, 7)
    assert m.sales_30d == Delta(300, 30)
    assert m.prev_sales_7d == Delta(100, 7)
    assert m.favorers_7d == Delta(5, 7)
    assert m.sales_per_listing == pytest.approx(20.0)


def test_shop_metrics_short_history_and_no_prev(session):
    add_shop(session, 1, [(3, 988, 10, 0), (0, 1000, 12, 0)])
    add_shop(session, 2, [(0, 500, 1, None)])
    add_shop(session, 3, [])
    session.commit()

    by_id = {m.shop.id: m for m in shop_metrics(session)}
    one = by_id[1]
    assert one.sales_7d == Delta(12, 3) and one.sales_30d == Delta(12, 3)
    assert one.prev_sales_7d is None
    assert one.sales_per_listing is None  # listing_count 0
    two = by_id[2]
    assert (two.sold_count, two.sales_7d, two.sales_30d, two.favorers_7d, two.sales_per_listing) == (
        500, None, None, None, None)
    three = by_id[3]
    assert (three.sold_count, three.listing_count, three.sales_7d) == (None, None, None)


def test_shop_metrics_uses_each_shops_own_latest_and_old_history(session):
    # shop 1 was last seen 60 days ago; its deltas are computed relative to its own latest snapshot
    add_shop(session, 1, [(67, 100, 0, 1), (60, 130, 0, 1)])
    # shop 2 has a snapshot 45 days ago and today: 30d window falls back to the 45-day-old one
    add_shop(session, 2, [(45, 100, 0, 1), (0, 400, 0, 1)])
    session.commit()

    by_id = {m.shop.id: m for m in shop_metrics(session)}
    assert by_id[1].sales_7d == Delta(30, 7)
    assert by_id[2].sales_30d == Delta(300, 45)
    assert by_id[2].sales_7d == Delta(300, 45)


def test_shop_metrics_restricted_to_ids(session):
    add_shop(session, 1, [(0, 1, 0, 1)])
    add_shop(session, 2, [(0, 2, 0, 1)])
    session.commit()

    assert [m.shop.id for m in shop_metrics(session, [2])] == [2]
    assert shop_metrics(session, []) == []


# --- shops_matching -------------------------------------------------------------------------

def add_product(session, shop_id, title, ext):
    session.add(Product(source="etsy", external_id=ext, title=title, url=f"https://etsy.com/{ext}",
                        product_type="tshirt", shop_id=shop_id))


def test_shops_matching_whole_word(session):
    add_shop(session, 1, [])
    add_shop(session, 2, [])
    add_shop(session, 3, [])
    add_product(session, 1, "Funny Nurse Shirt", "a")
    add_product(session, 2, "Nursery Rhyme Tee", "b")
    add_product(session, 3, "Nurses Week Gift", "c")
    add_product(session, None, "Nurse Hoodie", "d")
    session.commit()

    assert shops_matching(session, "nurse") == {1, 3}
    assert shops_matching(session, "NURSE") == {1, 3}
    assert shops_matching(session, "teacher") == set()
