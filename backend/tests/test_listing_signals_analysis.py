from datetime import date

import pytest

from app.analysis.listing_signals import (
    ListingMetrics,
    Thresholds,
    classify,
    compute_metrics,
    load_signals_config,
)
from app.analysis.velocity import SnapshotPoint

TODAY = date(2026, 10, 7)


def pt(d, views, saves):
    return SnapshotPoint(date=d, reviews=None, favorites=saves, views=views)


def test_load_config_from_yaml():
    cfg = load_signals_config()
    assert "graphic tee" in cfg.queries and "christmas shirt" in cfg.queries
    assert (cfg.pages_per_query, cfg.max_age_days, cfg.track_days, cfg.max_tracked) == (3, 30, 45, 20000)
    assert cfg.thresholds == Thresholds()


def test_metrics_from_two_days():
    m = compute_metrics([pt(date(2026, 10, 6), 100, 10), pt(TODAY, 160, 22)], date(2026, 10, 1), TODAY)
    assert (m.age_days, m.views, m.saves) == (6, 160, 22)
    assert m.delta_views == pytest.approx(60) and m.delta_saves == pytest.approx(12)
    assert m.dsr == pytest.approx(0.2)


def test_metrics_scale_by_span_and_pick_recent_base():
    points = [pt(date(2026, 10, 3), 10, 0), pt(date(2026, 10, 5), 50, 4), pt(TODAY, 90, 8)]
    m = compute_metrics(points, None, TODAY)
    assert m.delta_views == pytest.approx(20) and m.delta_saves == pytest.approx(2)  # base = Oct 5, span 2
    assert m.age_days is None


def test_metrics_need_a_day_apart_and_min_views_for_dsr():
    assert compute_metrics([pt(TODAY, 10, 1)], None, TODAY).delta_saves is None
    m = compute_metrics([pt(date(2026, 10, 6), 10, 1), pt(TODAY, 15, 3)], None, TODAY)
    assert m.delta_saves == pytest.approx(2) and m.dsr is None  # only 5 new views


def metrics(age, saves, dsave, dsr):
    return ListingMetrics(age_days=age, views=1000, saves=saves, delta_views=50, delta_saves=dsave, dsr=dsr)


@pytest.mark.parametrize(
    "m,expected",
    [
        (ListingMetrics(5, 10, 1, None, None, None), "calibrating"),
        (metrics(6, 22, 12, 0.2), "super_breakout"),
        (metrics(20, 22, 12, 0.2), "steady_grower"),  # too old for breakout
        (metrics(6, 22, 12, 0.10), "steady_grower"),  # DSR too low for breakout
        (metrics(35, 40, 1.5, 0.01), "graduated"),
        (metrics(10, 5, 2, 0.06), "steady_grower"),
        (metrics(10, 5, 1, 0.5), "normal"),
        (metrics(10, 5, 3, None), "normal"),  # no DSR → not steady
    ],
)
def test_classify(m, expected):
    assert classify(m, Thresholds()) == expected


def test_metrics_pick_base_per_metric_when_a_scan_is_missing_views():
    points = [pt(date(2026, 10, 5), 100, 10), pt(date(2026, 10, 6), None, 14), pt(TODAY, 160, 22)]
    m = compute_metrics(points, None, TODAY)
    assert (m.views, m.saves) == (160, 22)
    assert m.delta_views == pytest.approx(30)  # base Oct 5, span 2
    assert m.delta_saves == pytest.approx(8)  # base Oct 6, span 1
    assert m.dsr == pytest.approx(0.2)  # pair Oct 5 -> Oct 7


def test_decreasing_favorites_classify_normal():
    m = compute_metrics([pt(date(2026, 10, 6), 100, 20), pt(TODAY, 200, 15)], date(2026, 10, 1), TODAY)
    assert m.delta_saves == pytest.approx(-5)
    assert classify(m, Thresholds()) == "normal"


def test_dsr_min_views_boundary():
    at = compute_metrics([pt(date(2026, 10, 6), 100, 10), pt(TODAY, 110, 12)], None, TODAY)
    assert at.dsr == pytest.approx(0.2)
    below = compute_metrics([pt(date(2026, 10, 6), 100, 10), pt(TODAY, 109, 12)], None, TODAY)
    assert below.dsr is None


def test_classify_boundaries():
    t = Thresholds()
    assert classify(metrics(14, 22, 5.0, 0.15), t) == "super_breakout"
    assert classify(metrics(30, 40, 2, 0.01), t) == "normal"
    assert classify(metrics(31, 40, 2, 0.01), t) == "graduated"
