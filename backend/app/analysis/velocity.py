import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

MIN_SPAN_DAYS = 3
WINDOW_DAYS = 7


METRIC_PRIORITY = ("reviews", "views", "favorites")


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    reviews: int | None
    favorites: int | None
    views: int | None = None


def velocity_metric(snapshots: list[SnapshotPoint]) -> str | None:
    """Metric for the whole series: best available one on the latest snapshot that has any."""
    for point in sorted(snapshots, key=lambda p: p.date, reverse=True):
        for name in METRIC_PRIORITY:
            if getattr(point, name) is not None:
                return name
    return None


def compute_velocity(
    snapshots: list[SnapshotPoint], listed_on: date | None
) -> tuple[float | None, float | None]:
    """Return (delta over 7 days, delta per week of listing age) for one metric series."""
    metric = velocity_metric(snapshots)
    if metric is None:
        return None, None
    points = sorted((p for p in snapshots if getattr(p, metric) is not None), key=lambda p: p.date)
    if len(points) < 2:
        return None, None
    latest = points[-1]
    cutoff = latest.date - timedelta(days=WINDOW_DAYS)
    older = [p for p in points[:-1] if p.date <= cutoff]
    base = older[-1] if older else points[0]
    span = (latest.date - base.date).days
    if span < MIN_SPAN_DAYS:
        return None, None
    delta_7d = (getattr(latest, metric) - getattr(base, metric)) * WINDOW_DAYS / span
    weeks = (latest.date - listed_on).days / 7 if listed_on else 1.0
    return delta_7d, delta_7d / max(1.0, weeks)


def hot_ids(
    rows: Iterable[tuple[int, tuple[str, str], float | None]], top_fraction: float = 0.10
) -> set[int]:
    """Top `top_fraction` of positive velocities within each (source, product_type) group."""
    groups: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)
    for product_id, group, velocity in rows:
        if velocity is not None and velocity > 0:
            groups[group].append((velocity, product_id))
    hot: set[int] = set()
    for values in groups.values():
        values.sort(reverse=True)
        n = max(1, math.ceil(len(values) * top_fraction))
        hot.update(pid for _, pid in values[:n])
    return hot
