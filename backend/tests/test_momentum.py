from datetime import date, timedelta

import pytest

from app.analysis.momentum import MomentumConfig, steady_rate

D0 = date(2026, 10, 1)


def series(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_steady_growth_has_no_penalty():
    m = steady_rate(series([0, 5, 10, 15, 20]))
    assert m.rate == pytest.approx(5)
    assert m.top_share == pytest.approx(0.25)
    assert m.momentum == pytest.approx(5) and m.spike is False


def test_one_day_spike_is_penalised():
    m = steady_rate(series([0, 0, 0, 40, 40]))
    assert m.rate == pytest.approx(10)
    assert m.top_share == 1.0 and m.spike is True
    assert m.momentum == pytest.approx(3)  # full penalty: 10 × (1 − 0.7)


def test_partial_penalty_and_falls_count_as_zero():
    # gains 2, 0 (fall), 8, 0 → top share 0.8 → penalty 0.5 → × 0.65
    m = steady_rate(series([10, 12, 11, 19, 19]))
    assert m.top_share == pytest.approx(0.8)
    assert m.momentum == pytest.approx(m.rate * 0.65)


def test_too_few_gains_or_window_cut():
    assert steady_rate(series([0, 5, 10])) is None
    assert steady_rate([]) is None
    # only the last 7 days count: the old point is dropped, leaving 2 gains
    assert steady_rate([(D0, 0), (D0 + timedelta(days=20), 5), (D0 + timedelta(days=21), 6),
                        (D0 + timedelta(days=22), 7)]) is None
    assert steady_rate(series([0, 5, 10]), MomentumConfig(min_intervals=2)) is not None


def test_no_growth():
    m = steady_rate(series([3, 3, 3, 3]))
    assert m.momentum == 0 and m.top_share is None and m.spike is False
