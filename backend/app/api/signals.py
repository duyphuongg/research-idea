from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.listing_signals import SIGNAL_STATUSES, load_signals_config
from app.api.deps import get_session
from app.api.schemas import SignalItem, SignalPage, SignalTag
from app.keywords import canonical_keyword
from app.models import Keyword, ListingSignal, Product
from app.services.watchlist import listing_keyword_filter

router = APIRouter(prefix="/api")

SIGNAL_GROUP = ("super_breakout", "steady_grower", "graduated")
VISIBLE = tuple(s for s in SIGNAL_STATUSES if s != "gone")


@router.get("/signals", response_model=SignalPage)
def list_signals(
    status: str = "signals",
    max_age: int | None = Query(None, ge=1),
    keyword: str | None = None,
    sort: Literal["delta_saves", "dsr", "delta_views", "newest"] = "delta_saves",
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> SignalPage:
    if status == "signals":
        statuses = SIGNAL_GROUP
    elif status == "all":
        statuses = VISIBLE
    elif status in SIGNAL_STATUSES:
        statuses = (status,)
    else:
        raise HTTPException(422, f"invalid status: {status}")

    latest = session.scalar(select(func.max(ListingSignal.updated_on)))
    if latest is None:
        return SignalPage(updated_on=None, counts={}, total=0, items=[])

    base = [ListingSignal.updated_on == latest]
    if keyword:
        base.append(listing_keyword_filter(keyword, load_signals_config().seed_query_suffix))
    count_rows = session.execute(
        select(ListingSignal.status, func.count())
        .select_from(ListingSignal)
        .join(Product, Product.id == ListingSignal.product_id)
        .where(*base, ListingSignal.status != "gone")
        .group_by(ListingSignal.status)
    ).all()
    counts = {s: n for s, n in count_rows}

    filters = [*base, ListingSignal.status.in_(statuses)]
    if max_age is not None:
        filters.append(ListingSignal.age_days <= max_age)
    total = session.scalar(
        select(func.count()).select_from(ListingSignal)
        .join(Product, Product.id == ListingSignal.product_id).where(*filters)
    ) or 0

    if sort == "newest":
        order = [Product.listed_at.is_(None), Product.listed_at.desc()]
    else:
        col = getattr(ListingSignal, sort)
        order = [col.is_(None), col.desc()]
    rows = session.execute(
        select(ListingSignal, Product)
        .join(Product, Product.id == ListingSignal.product_id)
        .where(*filters)
        .order_by(*order, Product.id)
        .limit(limit)
        .offset(offset)
    ).all()

    tags_by_row = [[str(t) for t in (p.tags or [])] for _, p in rows]
    wanted = {x for tags in tags_by_row for t in tags for x in (canonical_keyword(t), t)}
    kw_ids = (
        dict(session.execute(select(Keyword.text, Keyword.id).where(Keyword.text.in_(wanted))).all())
        if wanted
        else {}
    )

    items = []
    for (sig, p), tags in zip(rows, tags_by_row):
        items.append(
            SignalItem(
                product_id=p.id, title=p.title, url=p.url, image_url=p.image_url,
                shop_name=p.shop_name, shop_sold_count=p.shop_sold_count,
                price=p.price, currency=p.currency, product_type=p.product_type,
                listed_at=p.listed_at, age_days=sig.age_days, views=sig.views,
                saves=sig.saves, delta_views=sig.delta_views, delta_saves=sig.delta_saves,
                dsr=sig.dsr, status=sig.status, discovery_query=sig.discovery_query,
                tags=[
                    SignalTag(tag=t, keyword_id=kw_ids.get(canonical_keyword(t), kw_ids.get(t)))
                    for t in tags
                ],
            )
        )
    return SignalPage(updated_on=latest, counts=counts, total=total, items=items)
