from collections import defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.listing_signals import load_signals_config
from app.api.deps import get_session
from app.api.schemas import WatchChild, WatchItem, WatchPage, WatchThumb
from app.db import utcnow
from app.models import Alert, Keyword, KeywordScore, ListingSignal, Product
from app.services.watchlist import (
    child_keyword_ids, listing_keyword_filter, seed_keyword_ids, watch_keywords,
)

router = APIRouter(prefix="/api")
SHOWN = ("super_breakout", "steady_grower")
MAX_CHILDREN = 3
MAX_THUMBS = 4


def _latest_scores(session: Session, ids: list[int]) -> dict[int, KeywordScore]:
    """Latest KeywordScore per keyword id (two bulk queries)."""
    if not ids:
        return {}
    latest = (select(KeywordScore.keyword_id, func.max(KeywordScore.date).label("d"))
              .where(KeywordScore.keyword_id.in_(ids)).group_by(KeywordScore.keyword_id).subquery())
    rows = session.scalars(select(KeywordScore).join(
        latest, (KeywordScore.keyword_id == latest.c.keyword_id) & (KeywordScore.date == latest.c.d)))
    return {s.keyword_id: s for s in rows}


@router.get("/watchlist", response_model=WatchPage)
def watchlist(session: Session = Depends(get_session)):
    seeds = watch_keywords(session)
    suffix = load_signals_config().seed_query_suffix
    latest_listing = session.scalar(select(func.max(ListingSignal.updated_on)))
    week_ago = utcnow() - timedelta(days=7)

    seed_kw = {}
    for seed in seeds:
        ids = seed_keyword_ids(session, seed.keyword)
        seed_kw[seed.id] = session.get(Keyword, ids[0]) if ids else None
    children = {seed.id: child_keyword_ids(session, seed.keyword) for seed in seeds}

    all_ids = {k.id for k in seed_kw.values() if k} | {i for ids in children.values() for i in ids}
    scores = _latest_scores(session, list(all_ids))
    kw_by_id = {k.id: k for k in session.scalars(select(Keyword).where(Keyword.id.in_(all_ids)))} if all_ids else {}
    alert_counts = dict(session.execute(
        select(Alert.watch_keyword, func.count()).where(Alert.created_at >= week_ago,
                                                         Alert.watch_keyword.is_not(None))
        .group_by(Alert.watch_keyword)).all())

    items = []
    for seed in seeds:
        kw = seed_kw[seed.id]
        own = scores.get(kw.id) if kw else None
        kids = sorted(
            ((kid, scores[kid].score) for kid in children[seed.id]
             if kid in scores and kid in kw_by_id and kw_by_id[kid].is_pod_relevant),
            key=lambda t: -t[1])
        relevant_total = sum(1 for kid in children[seed.id] if kid in kw_by_id and kw_by_id[kid].is_pod_relevant)

        counts: dict[str, int] = defaultdict(int)
        thumbs: list[WatchThumb] = []
        if latest_listing:
            rows = session.execute(
                select(ListingSignal.status, Product)
                .join(Product, Product.id == ListingSignal.product_id)
                .where(ListingSignal.updated_on == latest_listing, ListingSignal.status.in_(SHOWN),
                       listing_keyword_filter(seed.keyword, suffix))
                .order_by((ListingSignal.status != "super_breakout"),
                          ListingSignal.delta_saves.desc().nulls_last(), Product.id)).all()
            for status, product in rows:
                counts[status] += 1
                if len(thumbs) < MAX_THUMBS:
                    thumbs.append(WatchThumb(product_id=product.id, image_url=product.image_url,
                                             title=product.title, url=product.url, status=status))
        items.append(WatchItem(
            seed_id=seed.id, keyword=seed.keyword, keyword_id=kw.id if kw else None,
            score=own.score if own else None, growth=own.growth if own else None,
            children_total=relevant_total,
            children=[WatchChild(keyword_id=kid, keyword=kw_by_id[kid].text, score=s)
                      for kid, s in kids[:MAX_CHILDREN]],
            listings={s: counts.get(s, 0) for s in SHOWN},
            thumbnails=thumbs,
            alerts_7d=alert_counts.get(seed.keyword, 0),
        ))
    dates = [s.date for s in scores.values()]
    return WatchPage(date=max(dates) if dates else None, items=items)
