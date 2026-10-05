import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

MIN_SPAN_DAYS = 3
WINDOW_DAYS = 7


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    reviews: int | None
    favorites: int | None


def _chosen_metric_name(point: SnapshotPoint) -> str:
    """Return 'reviews' if reviews is not None, else 'favorites'."""
    return "reviews" if point.reviews is not None else "favorites"


def compute_velocity(
    snapshots: list[SnapshotPoint], listed_on: date | None
) -> tuple[float | None, float | None]:
    """Return (delta over 7 days, delta per week of listing age)."""
    # Sort first to find the latest snapshot
    sorted_snapshots = sorted(snapshots, key=lambda p: p.date)

    # Find the latest snapshot that has any metric
    latest_with_metric = None
    for p in reversed(sorted_snapshots):
        if p.reviews is not None or p.favorites is not None:
            latest_with_metric = p
            break

    if latest_with_metric is None:
        return None, None

    # Choose metric type based on latest snapshot
    metric_name = _chosen_metric_name(latest_with_metric)

    # Filter to only points with the chosen metric and sort
    points = sorted(
        (p for p in snapshots if getattr(p, metric_name) is not None),
        key=lambda p: p.date,
    )

    if len(points) < 2:
        return None, None

    latest = points[-1]
    cutoff = latest.date - timedelta(days=WINDOW_DAYS)
    older = [p for p in points[:-1] if p.date <= cutoff]
    base = older[-1] if older else points[0]
    span = (latest.date - base.date).days
    if span < MIN_SPAN_DAYS:
        return None, None
    delta_7d = (
        (getattr(latest, metric_name) - getattr(base, metric_name))
        * WINDOW_DAYS
        / span
    )
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
