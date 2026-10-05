from datetime import date

import pytest

from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids


def fav(d: date, n: int) -> SnapshotPoint:
    return SnapshotPoint(date=d, reviews=None, favorites=n)


def test_needs_two_snapshots():
    assert compute_velocity([fav(date(2026, 9, 27), 10)], None) == (None, None)


def test_needs_three_day_span():
    points = [fav(date(2026, 9, 25), 10), fav(date(2026, 9, 27), 20)]
    assert compute_velocity(points, None) == (None, None)


def test_weekly_delta_divided_by_weeks_since_listed():
    points = [fav(date(2026, 9, 20), 100), fav(date(2026, 9, 27), 170)]
    delta, velocity = compute_velocity(points, date(2026, 9, 13))
    assert delta == pytest.approx(70)
    assert velocity == pytest.approx(35)  # 2 weeks old


def test_baseline_is_closest_snapshot_seven_days_back():
    points = [
        fav(date(2026, 9, 17), 50),
        fav(date(2026, 9, 20), 100),
        fav(date(2026, 9, 24), 130),
        fav(date(2026, 9, 27), 170),
    ]
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(70)


def test_short_span_is_scaled_to_seven_days():
    points = [fav(date(2026, 9, 24), 130), fav(date(2026, 9, 27), 160)]
    delta, velocity = compute_velocity(points, None)
    assert delta == pytest.approx(70)
    assert velocity == pytest.approx(70)


def test_reviews_preferred_over_favorites():
    points = [
        SnapshotPoint(date(2026, 9, 20), reviews=10, favorites=999),
        SnapshotPoint(date(2026, 9, 27), reviews=24, favorites=0),
    ]
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(14)


def test_recent_listing_is_not_boosted_above_delta():
    points = [fav(date(2026, 9, 20), 0), fav(date(2026, 9, 27), 50)]
    _, velocity = compute_velocity(points, date(2026, 9, 25))
    assert velocity == pytest.approx(50)


def test_hot_ids_top_ten_percent_per_group():
    rows = [(i, ("etsy", "tshirt"), float(i)) for i in range(1, 21)]
    rows += [(100, ("etsy", "hoodie"), 5.0), (101, ("etsy", "hoodie"), None), (102, ("etsy", "hoodie"), -1.0)]
    assert hot_ids(rows) == {20, 19, 100}


def test_hot_ids_ignores_non_positive():
    assert hot_ids([(1, ("etsy", "tshirt"), 0.0), (2, ("etsy", "tshirt"), None)]) == set()


def test_mixed_metrics_do_not_cross_compare():
    """Metric must be chosen once per series; baseline and latest must use same metric."""
    points = [
        SnapshotPoint(date(2026, 9, 20), reviews=None, favorites=500),
        SnapshotPoint(date(2026, 9, 27), reviews=3, favorites=510),
    ]
    assert compute_velocity(points, None) == (None, None)


def test_falls_back_to_favorites_when_latest_has_no_reviews():
    """When latest has no reviews, use favorites for the entire series."""
    points = [
        SnapshotPoint(date(2026, 9, 20), reviews=3, favorites=100),
        SnapshotPoint(date(2026, 9, 27), reviews=None, favorites=170),
    ]
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(70)
