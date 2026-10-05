from datetime import date, timedelta

import pytest

from app.analysis.scoring import (
    Weights,
    latest_recent,
    load_weights,
    percentile_ranks,
    score_keywords,
    series_growth,
)

TODAY = date(2026, 10, 5)


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def test_load_weights_from_yaml():
    assert load_weights() == Weights(demand=0.35, momentum=0.45, competition=0.20)


def test_percentile_ranks():
    assert percentile_ranks({}) == {}
    assert percentile_ranks({1: 5.0}) == {1: 1.0}
    assert percentile_ranks({1: 1.0, 2: 2.0, 3: 3.0}) == {1: 0.0, 2: 0.5, 3: 1.0}
    assert percentile_ranks({1: 1.0, 2: 1.0, 3: 3.0}) == {1: 0.25, 2: 0.25, 3: 1.0}


def test_latest_recent_and_growth():
    series = [(days_ago(20), 10.0), (days_ago(10), 10.0), (days_ago(3), 12.0), (days_ago(1), 18.0)]
    assert latest_recent(series, TODAY) == 18.0
    assert series_growth(series, TODAY) == pytest.approx(0.5)  # mean(12,18)=15 vs 10
    assert latest_recent([(days_ago(8), 1.0)], TODAY) is None
    assert series_growth([(days_ago(1), 5.0)], TODAY) is None
    assert series_growth([(days_ago(1), 5.0), (days_ago(10), 0.0)], TODAY) is None


def test_score_keywords_end_to_end():
    signals = {
        # seed with rising Etsy demand and low competition
        1: {
            ("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 20.0)],
            ("etsy", "listing_count_tshirt"): [(days_ago(1), 1000.0)],
        },
        # seed with flat demand and high competition
        2: {
            ("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 10.0)],
            ("etsy", "listing_count_tshirt"): [(days_ago(1), 100000.0)],
        },
        # discovered suggestion: only demand, no history
        3: {("google_suggest", "suggest_score"): [(days_ago(0), 10.0)]},
        # stale keyword: no recent point → not scored
        4: {("google_daily", "traffic"): [(days_ago(9), 5000.0)]},
    }
    results = {r.keyword_id: r for r in score_keywords(signals, TODAY)}

    assert set(results) == {1, 2, 3}
    k1, k2, k3 = results[1], results[2], results[3]
    assert (k1.demand, k1.momentum, k1.competition) == (1.0, 1.0, 0.0)
    assert k1.growth == pytest.approx(1.0)
    assert (k1.sources, k1.sources_rising) == (("etsy",), 1)
    assert k1.score == 100.0
    assert (k2.demand, k2.momentum, k2.competition) == (0.0, 0.0, 1.0)
    assert k2.score == 0.0
    assert (k3.demand, k3.momentum, k3.competition, k3.growth) == (1.0, None, None, None)
    assert k3.score == 100.0  # only demand available → weight renormalized
    assert [r.keyword_id for r in score_keywords(signals, TODAY)] == [1, 3, 2]


def test_convergence_bonus_and_multi_source_demand():
    rising = [(days_ago(14), 10.0), (days_ago(1), 20.0)]
    flat = [(days_ago(14), 10.0), (days_ago(1), 10.0)]
    signals = {
        1: {("etsy", "views_per_day"): rising, ("google_suggest", "suggest_score"): rising},
        2: {("etsy", "views_per_day"): flat, ("google_suggest", "suggest_score"): rising},
        3: {("etsy", "views_per_day"): flat, ("google_suggest", "suggest_score"): flat},
    }
    results = {r.keyword_id: r for r in score_keywords(signals, TODAY, Weights(1.0, 1.0, 1.0))}
    assert results[1].sources_rising == 2
    assert results[1].momentum == 1.0  # 1.0 percentile + bonus, capped
    assert results[2].sources_rising == 1
    assert results[2].momentum == pytest.approx(0.5)
    assert results[3].momentum == 0.0
    # etsy pct 1.0 (20 vs 10,10); suggest pct 0.75 (tied 20,20 vs 10) → mean 0.875
    assert results[1].demand == pytest.approx(0.875)
