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


def test_config_loads_momentum_section():
    from app.analysis.momentum import MomentumConfig

    assert load_signals_config().momentum == MomentumConfig()


def _daily(saves):
    return [pt(date(2026, 10, 7 - len(saves) + 1 + i), 1000 + 50 * i, s) for i, s in enumerate(saves)]


def test_one_day_spike_is_not_a_breakout():
    # 40 saves in the last day only: the 1-day change says 40/day, the penalised rate says 40/4 × 0.3 = 3
    m = compute_metrics(_daily([0, 0, 0, 0, 40]), date(2026, 10, 1), TODAY)
    assert m.delta_saves == pytest.approx(40)
    assert m.spike is True and m.top_share == 1.0
    assert m.momentum == pytest.approx(3)
    assert classify(m, Thresholds()) == "steady_grower"  # 3/day ≥ 2, dsr 0.8 — no longer super breakout


def test_steady_growth_keeps_breakout():
    m = compute_metrics(_daily([0, 10, 20, 30, 40]), date(2026, 10, 1), TODAY)
    assert m.spike is False and m.momentum == pytest.approx(10)
    assert classify(m, Thresholds()) == "super_breakout"


def test_short_history_uses_one_day_change():
    m = compute_metrics(_daily([0, 40]), date(2026, 10, 1), TODAY)
    assert m.momentum is None and m.saves_per_day == pytest.approx(40)
    assert classify(m, Thresholds()) == "super_breakout"


def test_dsr_spans_the_window_when_views_lag():
    # views refreshed only every other day: the last 1-day pair has 0 new views
    points = [pt(date(2026, 10, 3), 100, 0), pt(date(2026, 10, 5), 200, 10), pt(date(2026, 10, 6), 300, 15),
              pt(TODAY, 300, 20)]
    m = compute_metrics(points, None, TODAY)
    assert m.delta_views == 0
    assert m.dsr == pytest.approx(0.1)  # 20 saves / 200 views since Oct 3
    old = [pt(date(2026, 9, 20), 0, 0), pt(date(2026, 10, 6), 300, 15), pt(TODAY, 300, 20)]
    assert compute_metrics(old, None, TODAY).dsr is None  # Sep 20 is outside the window; Oct 6 pair has 0 views
