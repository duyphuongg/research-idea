"""Keyword opportunity score (spec §13). Pure functions over trend_signals series."""

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import mean

from app.config_files import load_yaml

PRIMARY_METRICS = {
    "etsy": "views_per_day",
    "etsy_tags": "tag_count",
    "google_suggest": "suggest_score",
    "google_daily": "traffic",
}
COMPETITION_KEY = ("etsy", "listing_count_tshirt")
ACTIVE_DAYS = 7
HISTORY_DAYS = 30
RISING_GROWTH = 0.2
CONVERGENCE_BONUS = 0.1

Series = list[tuple[date, float]]


@dataclass(frozen=True)
class Weights:
    demand: float = 0.35
    momentum: float = 0.45
    competition: float = 0.20


@dataclass(frozen=True)
class KeywordScoreResult:
    keyword_id: int
    score: float
    demand: float | None
    momentum: float | None
    competition: float | None
    growth: float | None
    sources: tuple[str, ...]
    sources_rising: int


def load_weights() -> Weights:
    data = load_yaml("scoring.yaml").get("weights") or {}
    defaults = Weights()
    return Weights(
        demand=float(data.get("demand", defaults.demand)),
        momentum=float(data.get("momentum", defaults.momentum)),
        competition=float(data.get("competition", defaults.competition)),
    )


def percentile_ranks(values: dict[int, float]) -> dict[int, float]:
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {k: 1.0 for k in values}
    ordered = sorted(values.values())
    out = {}
    for key, value in values.items():
        less = bisect_left(ordered, value)
        equal = bisect_right(ordered, value) - less
        out[key] = (less + (equal - 1) / 2) / (n - 1)
    return out


def _window(series: Series, today: date, start: int, end: int) -> list[tuple[date, float]]:
    return [(d, v) for d, v in series if start <= (today - d).days < end]


def latest_recent(series: Series, today: date) -> float | None:
    recent = _window(series, today, 0, ACTIVE_DAYS)
    return max(recent)[1] if recent else None


def series_growth(series: Series, today: date) -> float | None:
    recent = [v for _, v in _window(series, today, 0, ACTIVE_DAYS)]
    older = [v for _, v in _window(series, today, ACTIVE_DAYS, HISTORY_DAYS)]
    if not recent or not older:
        return None
    base = mean(older)
    return mean(recent) / base - 1 if base > 0 else None


def _min_max(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if high == low:
        return {k: 0.5 for k in values}
    return {k: (v - low) / (high - low) for k, v in values.items()}


def score_keywords(
    signals: dict[int, dict[tuple[str, str], Series]], today: date, weights: Weights = Weights()
) -> list[KeywordScoreResult]:
    demand_raw: dict[str, dict[int, float]] = defaultdict(dict)
    growths: dict[int, dict[str, float]] = defaultdict(dict)
    competition_raw: dict[int, float] = {}
    active: dict[int, list[str]] = {}

    for keyword_id, by_metric in signals.items():
        sources = []
        for source, metric in PRIMARY_METRICS.items():
            series = by_metric.get((source, metric)) or []
            current = latest_recent(series, today)
            if current is None:
                continue
            sources.append(source)
            demand_raw[source][keyword_id] = current
            growth = series_growth(series, today)
            if growth is not None:
                growths[keyword_id][source] = growth
        if not sources:
            continue
        active[keyword_id] = sources
        listings = latest_recent(by_metric.get(COMPETITION_KEY) or [], today)
        if listings is not None:
            competition_raw[keyword_id] = math.log1p(listings)

    demand_pct = {source: percentile_ranks(values) for source, values in demand_raw.items()}
    mean_growth = {k: mean(g.values()) for k, g in growths.items() if g}
    momentum_pct = percentile_ranks(mean_growth)
    competition_norm = _min_max(competition_raw)

    results = []
    for keyword_id, sources in active.items():
        demand = mean(demand_pct[s][keyword_id] for s in sources)
        rising = sum(1 for g in growths.get(keyword_id, {}).values() if g > RISING_GROWTH)
        momentum = None
        if keyword_id in momentum_pct:
            momentum = min(1.0, momentum_pct[keyword_id] + CONVERGENCE_BONUS * max(0, rising - 1))
        competition = competition_norm.get(keyword_id)
        parts = [
            (weights.demand, demand),
            (weights.momentum, momentum),
            (weights.competition, None if competition is None else 1 - competition),
        ]
        available = [(w, v) for w, v in parts if v is not None]
        total = sum(w for w, _ in available)
        score = round(100 * sum(w * v for w, v in available) / total, 2) if total else 0.0
        results.append(
            KeywordScoreResult(
                keyword_id=keyword_id,
                score=score,
                demand=demand,
                momentum=momentum,
                competition=competition,
                growth=mean_growth.get(keyword_id),
                sources=tuple(sources),
                sources_rising=rising,
            )
        )
    return sorted(results, key=lambda r: (-r.score, r.keyword_id))
