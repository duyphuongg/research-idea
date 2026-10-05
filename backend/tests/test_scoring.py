from datetime import date, timedelta

import pytest

from app.analysis.scoring import (
    Weights,
    latest_recent,
    load_weights,
    percentile_ranks,
    score_keywords,
    series_growth,
    shrink,
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


def test_shrink():
    assert shrink(1.0, 1) == pytest.approx(0.6)
    assert shrink(1.0, 2) == pytest.approx(0.7)
    assert shrink(0.0, 5) == 0.0
    assert shrink(0.25, 10) == 0.25


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
    assert k1.demand == pytest.approx(0.7)
    assert k1.momentum == pytest.approx(0.8)  # 0.5 + 0.5 * shrink(1.0, 1)
    assert k1.competition == pytest.approx(0.3)  # shrink(0.0, 2)
    assert k1.growth == pytest.approx(1.0)
    assert (k1.sources, k1.sources_rising) == (("etsy",), 1)
    assert k1.score == 74.5
    assert k2.demand == pytest.approx(0.3)
    assert k2.momentum == 0.25  # flat growth
    assert k2.competition == pytest.approx(0.7)  # shrink(1.0, 2)
    assert k2.score == 27.75
    assert k3.demand == pytest.approx(0.6)
    assert (k3.momentum, k3.competition, k3.growth) == (None, None, None)
    assert k3.score == 53.5  # missing momentum/competition count as neutral 0.5
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
    assert results[1].momentum == pytest.approx(0.95)  # 0.5 + 0.5 * shrink(1.0, 2)=0.85 + bonus 0.1
    assert results[2].sources_rising == 1
    assert results[2].momentum == pytest.approx(0.65)  # 0.5 + 0.5 * shrink(0.0, 2)
    assert results[3].momentum == 0.25  # flat growth
    # etsy: shrink(1.0,3)=0.8; suggest: shrink(0.75,3)=0.65 → mean 0.725
    assert results[1].demand == pytest.approx(0.725)


def test_declining_keyword_gets_zero_momentum():
    signals = {1: {("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 4.0)]}}
    (result,) = score_keywords(signals, TODAY)
    assert result.growth == pytest.approx(-0.6)
    assert result.momentum == 0.0


def test_flat_keyword_gets_quarter_momentum():
    signals = {1: {("etsy", "views_per_day"): [(days_ago(14), 10.0), (days_ago(1), 10.3)]}}
    (result,) = score_keywords(signals, TODAY)
    assert result.growth == pytest.approx(0.03)
    assert result.momentum == 0.25
