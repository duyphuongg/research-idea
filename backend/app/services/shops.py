"""Shop Explorer metrics: orders/favorers over 7/30 days from daily shop snapshots."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product, Shop, ShopSnapshot
from app.services.watchlist import keyword_regex

# Snapshots older than this (relative to each shop's own latest snapshot) are never needed:
# 30-day window + the 7-day previous-week window + slack for gaps in daily scans.
HISTORY_DAYS = 45
# A shop whose latest snapshot is older than this (vs. the newest snapshot of any shop) is stale.
STALE_DAYS = 3
# A window's base snapshot may be up to this many days older than the window (missed daily scans).
WINDOW_SLACK_DAYS = 2


@dataclass(frozen=True)
class Delta:
    value: int
    days: int  # actual span the value covers


@dataclass(frozen=True)
class ShopMetrics:
    shop: Shop
    sold_count: int | None
    listing_count: int | None
    review_average: float | None
    sales_7d: Delta | None
    sales_30d: Delta | None
    prev_sales_7d: Delta | None
    favorers_7d: Delta | None
    sales_per_listing: float | None
    review_count: int | None = None


def window_delta(points: list[tuple[date, int | None]], latest: date, days: int) -> Delta | None:
    """Latest value minus the value at the newest snapshot at least `days` before `latest`.

    That base is used only when it is at most `days + WINDOW_SLACK_DAYS` before `latest`; otherwise
    (gaps in the history, or history younger than the window) the oldest snapshot inside the window
    is used and `days` is the actual, shorter span. Points dated after `latest` and points with a None
    value are ignored. None with < 2 usable points, no base, or a 0-day span.
    """
    usable = sorted((d, v) for d, v in points if v is not None and d <= latest)
    if len(usable) < 2:
        return None
    end_date, end_value = usable[-1]
    cutoff = latest - timedelta(days=days)
    older = [p for p in usable if p[0] <= cutoff]
    if older and (latest - older[-1][0]).days <= days + WINDOW_SLACK_DAYS:
        base_date, base_value = older[-1]
    else:
        inside = [p for p in usable[:-1] if p[0] > cutoff]
        if not inside:
            return None
        base_date, base_value = inside[0]
    span = (end_date - base_date).days
    if span <= 0:
        return None
    return Delta(value=end_value - base_value, days=span)


def is_full_window(delta: Delta | None, days: int) -> bool:
    """True when `delta` covers the whole `days` window (allowing the gap slack)."""
    return delta is not None and days <= delta.days <= days + WINDOW_SLACK_DAYS


def _prev_week(points: list[tuple[date, int | None]], latest: date) -> Delta | None:
    """The 7-day delta ending 7 days before `latest`; needs history reaching back 14 days."""
    dated = [d for d, v in points if v is not None]
    if not dated or min(dated) > latest - timedelta(days=14):
        return None
    return window_delta(points, latest - timedelta(days=7), 7)


def shop_metrics(session: Session, shop_ids: Iterable[int] | None = None) -> list[ShopMetrics]:
    """Metrics for all shops (or the given ids), ordered by shop id. Two bulk queries."""
    shop_q = select(Shop).order_by(Shop.id)
    snap_q = select(
        ShopSnapshot.shop_id, ShopSnapshot.date, ShopSnapshot.sold_count, ShopSnapshot.favorers,
        ShopSnapshot.listing_count, ShopSnapshot.review_average, ShopSnapshot.review_count,
    )
    latest = select(ShopSnapshot.shop_id, func.max(ShopSnapshot.date).label("d")).group_by(ShopSnapshot.shop_id)
    if shop_ids is not None:
        ids = list(shop_ids)
        if not ids:
            return []
        shop_q = shop_q.where(Shop.id.in_(ids))
        latest = latest.where(ShopSnapshot.shop_id.in_(ids))
    latest_sq = latest.subquery()
    # Dates are stored as ISO strings, so SQLite's date() arithmetic compares correctly.
    snap_q = snap_q.join(latest_sq, latest_sq.c.shop_id == ShopSnapshot.shop_id).where(
        ShopSnapshot.date >= func.date(latest_sq.c.d, f"-{HISTORY_DAYS} days")
    ).order_by(ShopSnapshot.shop_id, ShopSnapshot.date)

    # Plain tuples, grouped per shop: (date, sold, favorers, listings, rating, reviews)
    rows_by_shop: dict[int, list[tuple]] = defaultdict(list)
    for shop_id, *rest in session.execute(snap_q):
        rows_by_shop[shop_id].append(rest)

    global_latest = session.scalar(select(func.max(ShopSnapshot.date)))

    result = []
    for shop in session.scalars(shop_q):
        rows = rows_by_shop.get(shop.id)
        if not rows:
            result.append(ShopMetrics(shop, None, None, None, None, None, None, None, None, None))
            continue
        latest_date, last_sold, _, last_listings, last_rating, last_reviews = rows[-1]
        sold = [(r[0], r[1]) for r in rows]
        favs = [(r[0], r[2]) for r in rows]
        stale = global_latest is not None and latest_date < global_latest - timedelta(days=STALE_DAYS)
        spl = last_sold / last_listings if last_sold is not None and last_listings else None
        result.append(ShopMetrics(
            shop=shop,
            sold_count=last_sold,
            listing_count=last_listings,
            review_average=last_rating,
            sales_7d=None if stale else window_delta(sold, latest_date, 7),
            sales_30d=None if stale else window_delta(sold, latest_date, 30),
            prev_sales_7d=None if stale else _prev_week(sold, latest_date),
            favorers_7d=None if stale else window_delta(favs, latest_date, 7),
            sales_per_listing=spl,
            review_count=last_reviews,
        ))
    return result


def shops_matching(session: Session, keyword: str) -> set[int]:
    """Shops with at least one product whose title contains `keyword` as a whole word."""
    pattern = "(?i)" + keyword_regex(keyword)
    return set(session.scalars(
        select(Product.shop_id).where(Product.shop_id.is_not(None), Product.title.regexp_match(pattern)).distinct()
    ))
