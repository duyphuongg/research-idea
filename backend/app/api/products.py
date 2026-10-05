from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids, velocity_metric
from app.api.deps import get_session
from app.api.schemas import ProductOut, ProductPage
from app.models import Keyword, Product, ProductKeyword

router = APIRouter(prefix="/api")

SortKey = Literal["velocity", "reviews", "price", "newest"]


def _desc_none_last(value: float | None) -> tuple[bool, float]:
    return (value is None, -(value or 0))


SORTS: dict[str, Callable[[ProductOut], Any]] = {
    "velocity": lambda p: _desc_none_last(p.velocity),
    "reviews": lambda p: _desc_none_last(
        next((v for v in (p.reviews, p.views, p.favorites) if v is not None), None)
    ),
    "price": lambda p: (p.price is None, p.price or 0),
    "newest": lambda p: _desc_none_last(p.listed_at.timestamp() if p.listed_at else None),
}


@router.get("/products", response_model=ProductPage)
def list_products(
    source: str | None = None,
    product_type: str | None = Query(None, alias="type"),
    keyword_id: int | None = None,
    sort: SortKey = "velocity",
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ProductPage:
    products = session.scalars(
        select(Product)
        .order_by(Product.id)
        .options(selectinload(Product.snapshots))
    ).all()

    points = {
        p.id: [SnapshotPoint(s.date, s.reviews, s.favorites, s.views) for s in p.snapshots]
        for p in products
    }
    metrics = {
        p.id: compute_velocity(points[p.id], p.listed_at.date() if p.listed_at else None)
        for p in products
    }
    hot = hot_ids((p.id, (p.source, p.product_type), metrics[p.id][1]) for p in products)

    keyword_texts: dict[int, list[str]] = defaultdict(list)
    keyword_ids: dict[int, set[int]] = defaultdict(set)
    rows = session.execute(
        select(ProductKeyword.product_id, Keyword.id, Keyword.text).join(
            Keyword, Keyword.id == ProductKeyword.keyword_id
        )
    )
    for product_id, kid, text in rows:
        keyword_texts[product_id].append(text)
        keyword_ids[product_id].add(kid)

    items = [
        _to_out(p, metrics[p.id], velocity_metric(points[p.id]), p.id in hot, sorted(keyword_texts[p.id]))
        for p in products
        if (source is None or p.source == source)
        and (product_type is None or p.product_type == product_type)
        and (keyword_id is None or keyword_id in keyword_ids[p.id])
    ]
    items.sort(key=SORTS[sort])
    return ProductPage(total=len(items), items=items[offset : offset + limit])


def _to_out(
    p: Product, metric: tuple[float | None, float | None], metric_name: str | None, hot: bool, keywords: list[str]
) -> ProductOut:
    latest = p.snapshots[-1] if p.snapshots else None
    return ProductOut(
        id=p.id,
        source=p.source,
        title=p.title,
        url=p.url,
        image_url=p.image_url,
        shop_name=p.shop_name,
        price=p.price,
        currency=p.currency,
        product_type=p.product_type,
        listed_at=p.listed_at,
        reviews=latest.reviews if latest else None,
        favorites=latest.favorites if latest else None,
        rating=latest.rating if latest else None,
        views=latest.views if latest else None,
        shop_sold_count=p.shop_sold_count,
        velocity_metric=metric_name,
        delta_7d=metric[0],
        velocity=metric[1],
        hot=hot,
        keywords=keywords,
    )
