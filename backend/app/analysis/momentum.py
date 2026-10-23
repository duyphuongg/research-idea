"""Spike-penalised growth rate of a cumulative counter (e.g. a listing's saves)."""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class MomentumConfig:
    window_days: int = 7
    min_intervals: int = 3  # daily gains needed before the penalty is trusted
    spike_share: float = 0.6  # one gain above this share of the total counts as a spike …
    max_penalty: float = 0.7  # … and at most cuts the rate by this fraction (all growth in one day)


@dataclass(frozen=True)
class Momentum:
    rate: float  # per day over the window, before the penalty
    top_share: float | None  # largest single gain / total gain (None when nothing was gained)
    momentum: float  # rate after the spike penalty
    spike: bool


def steady_rate(points: list[tuple[date, int]], cfg: MomentumConfig = MomentumConfig()) -> Momentum | None:
    """Growth over the last `window_days` of a cumulative series, penalised when one gain dominates.

    Gains are taken between consecutive points (falls count as 0). None when fewer than
    `min_intervals` gains fall inside the window.
    """
    ordered = sorted(points)
    if not ordered:
        return None
    cutoff = ordered[-1][0] - timedelta(days=cfg.window_days)
    inside = [p for p in ordered if p[0] >= cutoff]
    gains = [max(0, b[1] - a[1]) for a, b in zip(inside, inside[1:]) if b[0] > a[0]]
    if len(gains) < cfg.min_intervals:
        return None
    span = (inside[-1][0] - inside[0][0]).days
    total = sum(gains)
    rate = total / span
    if total == 0:
        return Momentum(0.0, None, 0.0, False)
    top_share = max(gains) / total
    penalty = max(0.0, top_share - cfg.spike_share) / (1 - cfg.spike_share)
    return Momentum(rate, top_share, rate * (1 - cfg.max_penalty * penalty), top_share > cfg.spike_share)
