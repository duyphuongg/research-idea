from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.amazon import load_amazon_config
from app.api.deps import get_session
from app.api.schemas import AmazonCategoryOut, AmazonItem, AmazonPage
from app.models import AmazonRank, Product, ProductSnapshot

router = APIRouter(prefix="/api")
NEW_ENTRY_DAYS = 7


@router.get("/amazon", response_model=AmazonPage)
def amazon_ranks(
    category: str | None = None,
    list_name: str = Query("bestsellers", alias="list"),
    hide_licensed: bool = False,
    session: Session = Depends(get_session),
) -> AmazonPage:
    config = load_amazon_config()
    categories = [
        AmazonCategoryOut(key=c.key, product_type=c.product_type) for c in config.categories
    ]
    keys = [c.key for c in config.categories]
    if category is None:
        if not keys:
            raise HTTPException(status_code=422, detail="No Amazon categories configured")
        category = keys[0]
    if category not in keys:
        raise HTTPException(status_code=422, detail="Unknown category")
    if list_name not in config.lists:
        raise HTTPException(status_code=422, detail="Unknown list")

    def page(items: list[AmazonItem], day) -> AmazonPage:
        return AmazonPage(
            date=day, category=category, list=list_name, categories=categories, items=items
        )

    scope = (AmazonRank.category_key == category, AmazonRank.list_name == list_name)
    latest = session.scalar(select(func.max(AmazonRank.date)).where(*scope))
    if latest is None:
        return page([], None)

    rows = session.execute(
        select(AmazonRank, Product)
        .join(Product, Product.id == AmazonRank.product_id)
        .where(*scope, AmazonRank.date == latest)
        .order_by(AmazonRank.rank, AmazonRank.id)
    ).all()
    ids = [p.id for _, p in rows]

    # Most recent earlier rank per product within the last NEW_ENTRY_DAYS days.
    prev: dict[int, int] = {}
    recent: set[int] = set()
    since = latest - timedelta(days=NEW_ENTRY_DAYS)
    for pid, rank in session.execute(
        select(AmazonRank.product_id, AmazonRank.rank)
        .where(
            *scope,
            AmazonRank.product_id.in_(ids),
            AmazonRank.date < latest,
            AmazonRank.date >= since,
        )
        .order_by(AmazonRank.date)
    ):
        prev[pid] = rank
        recent.add(pid)
    window_has_history = (
        session.scalar(
            select(func.count())
            .select_from(AmazonRank)
            .where(*scope, AmazonRank.date < latest, AmazonRank.date >= since)
        )
        or 0
    ) > 0
    # Product in an earlier row older than the window still has a prev_rank.
    for pid in set(ids) - set(prev):
        older = session.scalar(
            select(AmazonRank.rank)
            .where(*scope, AmazonRank.product_id == pid, AmazonRank.date < latest)
            .order_by(AmazonRank.date.desc())
            .limit(1)
        )
        if older is not None:
            prev[pid] = older

    snaps: dict[int, ProductSnapshot] = {}
    for snap in session.scalars(
        select(ProductSnapshot)
        .where(ProductSnapshot.product_id.in_(ids))
        .order_by(ProductSnapshot.date)
    ):
        snaps[snap.product_id] = snap

    items = []
    for rank_row, product in rows:
        if hide_licensed and product.licensed:
            continue
        prev_rank = prev.get(product.id)
        snap = snaps.get(product.id)
        items.append(
            AmazonItem(
                product_id=product.id,
                asin=product.external_id,
                rank=rank_row.rank,
                prev_rank=prev_rank,
                rank_change=None if prev_rank is None else prev_rank - rank_row.rank,
                is_new_entry=window_has_history and product.id not in recent,
                title=product.title,
                url=product.url,
                image_url=product.image_url,
                rating=snap.rating if snap else None,
                reviews=snap.reviews if snap else None,
                product_type=product.product_type,
                licensed=product.licensed,
            )
        )
    return page(items, latest)
