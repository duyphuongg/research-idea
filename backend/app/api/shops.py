from collections import defaultdict
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.analysis.velocity import SnapshotPoint, compute_velocity, velocity_metric
from app.api.deps import get_session
from app.api.products import _to_out
from app.api.schemas import DeltaOut, ShopDetail, ShopOut, ShopPage, ShopPoint
from app.db import utcnow
from app.models import Keyword, Product, ProductKeyword, Shop, ShopSnapshot
from app.services.hot import ProductMetrics, compute_product_metrics
from app.services.shops import Delta, ShopMetrics, is_full_window, shop_metrics, shops_matching

router = APIRouter(prefix="/api")

ShopSort = Literal[
    "sales_7d", "sales_30d", "sold_count", "sales_per_listing", "opened_at", "listing_count",
    "review_average", "last_seen",
]
ListingsBand = Literal["lt200", "200_1000", "gt1000"]
OpenedBand = Literal["2026", "2025plus", "2024plus", "before2024"]
SERIES_DAYS = 90
MAX_PRODUCTS = 24

SORT_VALUES: dict[str, Callable[[ShopMetrics], Any]] = {
    "sales_7d": lambda m: m.sales_7d.value if m.sales_7d else None,
    "sales_30d": lambda m: m.sales_30d.value if m.sales_30d else None,
    "sold_count": lambda m: m.sold_count,
    "sales_per_listing": lambda m: m.sales_per_listing,
    "opened_at": lambda m: m.shop.opened_at,
    "listing_count": lambda m: m.listing_count,
    "review_average": lambda m: m.review_average,
    "last_seen": lambda m: m.shop.last_seen,
}

LISTING_BANDS: dict[str, Callable[[int], bool]] = {
    "lt200": lambda n: n < 200,
    "200_1000": lambda n: 200 <= n <= 1000,
    "gt1000": lambda n: n > 1000,
}

OPENED_BANDS: dict[str, Callable[[int], bool]] = {
    "2026": lambda y: y == 2026,
    "2025plus": lambda y: y >= 2025,
    "2024plus": lambda y: y >= 2024,
    "before2024": lambda y: y < 2024,
}


def _delta(d: Delta | None) -> DeltaOut | None:
    return DeltaOut(value=d.value, days=d.days) if d else None


def _shop_out(m: ShopMetrics) -> ShopOut:
    s = m.shop
    return ShopOut(
        id=s.id, name=s.name, url=s.url, icon_url=s.icon_url,
        opened_year=s.opened_at.year if s.opened_at else None,
        listing_count=m.listing_count, sold_count=m.sold_count,
        sales_7d=_delta(m.sales_7d), sales_30d=_delta(m.sales_30d), favorers_7d=_delta(m.favorers_7d),
        sales_per_listing=m.sales_per_listing, review_average=m.review_average, review_count=m.review_count,
        watched=s.watched_at is not None, last_seen=s.last_seen,
    )


def _at_least(value: float | None, minimum: float | None) -> bool:
    return minimum is None or (value is not None and value >= minimum)


# Sales sorts: values covering the full window rank before shorter (partial) spans, in either order.
SALES_WINDOWS: dict[str, tuple[Callable[[ShopMetrics], Delta | None], int]] = {
    "sales_7d": (lambda m: m.sales_7d, 7),
    "sales_30d": (lambda m: m.sales_30d, 30),
}


def _sorted(metrics: list[ShopMetrics], sort: str, order: str) -> list[ShopMetrics]:
    """Sort by `sort` in `order`; shops without a value always go last (stable within ties).

    For sales_7d / sales_30d, full-window values come first, then partial spans, each group by value.
    """
    key = SORT_VALUES[sort]
    present = [m for m in metrics if key(m) is not None]
    missing = [m for m in metrics if key(m) is None]
    groups = [present]
    if sort in SALES_WINDOWS:
        get, days = SALES_WINDOWS[sort]
        groups = [[m for m in present if is_full_window(get(m), days)],
                  [m for m in present if not is_full_window(get(m), days)]]
    out: list[ShopMetrics] = []
    for group in groups:
        out += sorted(group, key=key, reverse=order == "desc")
    return out + missing


@router.get("/shops", response_model=ShopPage)
def list_shops(
    q: str | None = None,
    min_sales: int | None = None,
    listings: ListingsBand | None = None,
    min_spl: float | None = None,
    opened: OpenedBand | None = None,
    min_rating: float | None = None,
    watched: bool | None = None,
    sort: ShopSort = "sales_7d",
    order: Literal["desc", "asc"] = "desc",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ShopPage:
    ids = shops_matching(session, q) if q and q.strip() else None
    metrics = shop_metrics(session, ids)
    items = [
        m for m in metrics
        if _at_least(m.sold_count, min_sales)
        and (listings is None or (m.listing_count is not None and LISTING_BANDS[listings](m.listing_count)))
        and _at_least(m.sales_per_listing, min_spl)
        and (opened is None or (m.shop.opened_at is not None and OPENED_BANDS[opened](m.shop.opened_at.year)))
        and _at_least(m.review_average, min_rating)
        and (watched is None or (m.shop.watched_at is not None) == watched)
    ]
    items = _sorted(items, sort, order)
    latest_date = session.scalar(select(func.max(ShopSnapshot.date)))
    return ShopPage(total=len(items), latest_date=latest_date,
                    items=[_shop_out(m) for m in items[offset: offset + limit]])


def _metrics_or_404(session: Session, shop_id: int) -> ShopMetrics:
    found = shop_metrics(session, [shop_id])
    if not found:
        raise HTTPException(404, "shop not found")
    return found[0]


def _shop_products(session: Session, shop_id: int):
    """The shop's newest products in the /api/products item shape."""
    products = list(session.scalars(
        select(Product).where(Product.shop_id == shop_id)
        .order_by(Product.listed_at.desc().nulls_last(), Product.id.desc())
        .limit(MAX_PRODUCTS).options(selectinload(Product.snapshots))
    ))
    if not products:
        return []
    _, population = compute_product_metrics(session)  # hot flags are relative to the Best Sellers population
    keywords: dict[int, list[str]] = defaultdict(list)
    for product_id, text in session.execute(
        select(ProductKeyword.product_id, Keyword.text).join(Keyword, Keyword.id == ProductKeyword.keyword_id)
        .where(ProductKeyword.product_id.in_([p.id for p in products]))
    ):
        keywords[product_id].append(text)
    out = []
    for p in products:
        m = population.get(p.id)
        if m is None:  # e.g. a Listing Signals-only listing: same velocity maths, never "hot"
            points = [SnapshotPoint(s.date, s.reviews, s.favorites, s.views) for s in p.snapshots]
            delta, velocity = compute_velocity(points, p.listed_at.date() if p.listed_at else None)
            m = ProductMetrics(delta, velocity, velocity_metric(points), False)
        out.append(_to_out(p, m, sorted(keywords[p.id])))
    return out


@router.get("/shops/{shop_id}", response_model=ShopDetail)
def shop_detail(shop_id: int, session: Session = Depends(get_session)) -> ShopDetail:
    m = _metrics_or_404(session, shop_id)
    latest = session.scalar(select(func.max(ShopSnapshot.date)).where(ShopSnapshot.shop_id == shop_id))
    series = []
    if latest is not None:
        series = [
            ShopPoint(date=s.date, sold_count=s.sold_count, favorers=s.favorers)
            for s in session.scalars(
                select(ShopSnapshot).where(ShopSnapshot.shop_id == shop_id,
                                           ShopSnapshot.date > latest - timedelta(days=SERIES_DAYS))
                .order_by(ShopSnapshot.date)
            )
        ]
    return ShopDetail(**_shop_out(m).model_dump(), series=series, products=_shop_products(session, shop_id))


def _set_watched(session: Session, shop_id: int, watched: bool) -> ShopOut:
    shop = session.get(Shop, shop_id)
    if shop is None:
        raise HTTPException(404, "shop not found")
    if watched and shop.watched_at is None:
        shop.watched_at = utcnow()
    elif not watched:
        shop.watched_at = None
    session.commit()
    return _shop_out(_metrics_or_404(session, shop_id))


@router.post("/shops/{shop_id}/watch", response_model=ShopOut)
def watch_shop(shop_id: int, session: Session = Depends(get_session)) -> ShopOut:
    return _set_watched(session, shop_id, True)


@router.delete("/shops/{shop_id}/watch", response_model=ShopOut)
def unwatch_shop(shop_id: int, session: Session = Depends(get_session)) -> ShopOut:
    return _set_watched(session, shop_id, False)
