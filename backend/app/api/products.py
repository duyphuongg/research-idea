from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ProductOut, ProductPage
from app.models import Keyword, Product, ProductKeyword
from app.services.hot import ProductMetrics, compute_product_metrics

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
    hide_licensed: bool = False,
    session: Session = Depends(get_session),
) -> ProductPage:
    products, metrics = compute_product_metrics(session)

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
        _to_out(p, metrics[p.id], sorted(keyword_texts[p.id]))
        for p in products
        if (source is None or p.source == source)
        and (product_type is None or p.product_type == product_type)
        and (keyword_id is None or keyword_id in keyword_ids[p.id])
        and not (hide_licensed and p.licensed)
    ]
    items.sort(key=SORTS[sort])
    return ProductPage(total=len(items), items=items[offset : offset + limit])


def _to_out(
    p: Product, m: ProductMetrics, keywords: list[str]
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
        velocity_metric=m.metric,
        delta_7d=m.delta_7d,
        velocity=m.velocity,
        hot=m.hot,
        keywords=keywords,
        licensed=p.licensed,
    )
