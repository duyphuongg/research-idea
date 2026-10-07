"""Etsy Listing Signals: config, per-listing growth metrics and classification (pure)."""

from dataclasses import dataclass, field, fields
from datetime import date, timedelta

from app.analysis.velocity import SnapshotPoint
from app.config_files import load_yaml

SIGNAL_STATUSES = ("super_breakout", "steady_grower", "graduated", "calibrating", "normal")
BREAKOUT_STATUSES = ("super_breakout", "steady_grower")


@dataclass(frozen=True)
class Thresholds:
    breakout_max_age: int = 14
    breakout_min_saves_per_day: float = 5.0
    breakout_min_dsr: float = 0.15
    graduated_min_age: int = 30
    graduated_min_saves: int = 30
    graduated_min_saves_per_day: float = 1.0
    steady_min_saves_per_day: float = 2.0
    steady_min_dsr: float = 0.05
    dsr_min_delta_views: int = 10


@dataclass(frozen=True)
class SignalsConfig:
    queries: tuple[str, ...]
    seed_query_suffix: str = "shirt"
    pages_per_query: int = 3
    max_age_days: int = 30
    track_days: int = 45
    max_tracked: int = 20000
    min_tag_listings: int = 2
    max_tags: int = 50
    thresholds: Thresholds = field(default_factory=Thresholds)


@dataclass(frozen=True)
class ListingMetrics:
    age_days: int | None
    views: int | None
    saves: int | None
    delta_views: float | None
    delta_saves: float | None
    dsr: float | None


def load_signals_config() -> SignalsConfig:
    data = load_yaml("listing_signals.yaml")
    raw = data.get("thresholds") or {}
    names = {f.name: f.type for f in fields(Thresholds)}
    thresholds = Thresholds(
        **{
            k: (int(v) if names[k] in (int, "int") else float(v))
            for k, v in raw.items()
            if k in names
        }
    )
    defaults = SignalsConfig(queries=())
    return SignalsConfig(
        queries=tuple(str(q) for q in data.get("queries") or ()),
        seed_query_suffix=str(data.get("seed_query_suffix", defaults.seed_query_suffix)),
        pages_per_query=int(data.get("pages_per_query", defaults.pages_per_query)),
        max_age_days=int(data.get("max_age_days", defaults.max_age_days)),
        track_days=int(data.get("track_days", defaults.track_days)),
        max_tracked=int(data.get("max_tracked", defaults.max_tracked)),
        min_tag_listings=int(data.get("min_tag_listings", defaults.min_tag_listings)),
        max_tags=int(data.get("max_tags", defaults.max_tags)),
        thresholds=thresholds,
    )


def compute_metrics(
    points: list[SnapshotPoint],
    listed_on: date | None,
    today: date,
    min_dsr_views: int = Thresholds().dsr_min_delta_views,
) -> ListingMetrics:
    usable = sorted(
        (p for p in points if p.views is not None or p.favorites is not None),
        key=lambda p: p.date,
    )
    age = (today - listed_on).days if listed_on else None
    if not usable:
        return ListingMetrics(age, None, None, None, None, None)
    latest = usable[-1]
    earlier = [p for p in usable[:-1] if p.date <= latest.date - timedelta(days=1)]
    base = earlier[-1] if earlier else None
    delta_views = delta_saves = dsr = None
    if base is not None:
        span = (latest.date - base.date).days
        if latest.views is not None and base.views is not None:
            delta_views = (latest.views - base.views) / span
        if latest.favorites is not None and base.favorites is not None:
            delta_saves = (latest.favorites - base.favorites) / span
        if delta_views is not None and delta_saves is not None:
            total_views = latest.views - base.views
            if total_views >= min_dsr_views:
                dsr = (latest.favorites - base.favorites) / total_views
    return ListingMetrics(age, latest.views, latest.favorites, delta_views, delta_saves, dsr)


def classify(m: ListingMetrics, t: Thresholds) -> str:
    if m.delta_saves is None:
        return "calibrating"
    age = m.age_days if m.age_days is not None else 0
    if (
        age <= t.breakout_max_age
        and m.delta_saves >= t.breakout_min_saves_per_day
        and m.dsr is not None
        and m.dsr >= t.breakout_min_dsr
    ):
        return "super_breakout"
    if (
        age > t.graduated_min_age
        and (m.saves or 0) >= t.graduated_min_saves
        and m.delta_saves >= t.graduated_min_saves_per_day
    ):
        return "graduated"
    if (
        m.delta_saves >= t.steady_min_saves_per_day
        and m.dsr is not None
        and m.dsr >= t.steady_min_dsr
    ):
        return "steady_grower"
    return "normal"
