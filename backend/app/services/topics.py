"""Ngách mới nổi: build topics from tracked Etsy listings after each scan, and read them back for the API."""

import zlib
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.analysis.product_type import is_digital_listing
from app.analysis.topics import ListingGain, TopicsConfig, build_topics, load_topics_config
from app.models import Product, ProductSnapshot, TopicSnapshot
from app.services.ip import ip_index
from app.services.shops import window_delta

WINDOW_DAYS = 7
MIN_SPAN_DAYS = 3  # a gain over fewer days is too noisy to scale to a week
HISTORY_DAYS = 2 * WINDOW_DAYS + 2  # this week, the week before, and slack for a missed scan
FRESH_DAYS = 1  # a listing not refreshed this recently (no longer tracked) is left out
SERIES_DAYS = 30
SAMPLE_PRODUCTS = 4


def topic_subject_id(key: str) -> int:
    """Stable positive int for a topic key (alerts need an integer subject id)."""
    return zlib.crc32(key.encode()) & 0x7FFFFFFF


def _scaled(points: list[tuple[date, int | None]], end: date) -> float | None:
    delta = window_delta(points, end, WINDOW_DAYS)
    if delta is None or delta.days < MIN_SPAN_DAYS:
        return None
    return max(0.0, delta.value * WINDOW_DAYS / delta.days)


def listing_gains(session: Session) -> list[ListingGain]:
    """Saves gained this week and last week by every recently refreshed, tagged, unlicensed Etsy listing."""
    ref = session.scalar(select(func.max(ProductSnapshot.date)))
    if ref is None:
        return []
    products = {
        pid: (shop_id, tags)
        for pid, shop_id, tags, title, licensed in session.execute(
            select(Product.id, Product.shop_id, Product.tags, Product.title, Product.licensed)
            .where(Product.source == "etsy", Product.tags.is_not(None))
        )
        if tags and not licensed and not is_digital_listing(title)
    }
    points: dict[int, list[tuple[date, int | None]]] = defaultdict(list)
    for pid, d, fav in session.execute(
        select(ProductSnapshot.product_id, ProductSnapshot.date, ProductSnapshot.favorites)
        .where(ProductSnapshot.date >= ref - timedelta(days=HISTORY_DAYS), ProductSnapshot.favorites.is_not(None))
        .order_by(ProductSnapshot.product_id, ProductSnapshot.date)
    ):
        if pid in products:
            points[pid].append((d, fav))
    out = []
    for pid, pts in points.items():
        if pts[-1][0] < ref - timedelta(days=FRESH_DAYS):
            continue
        gain = _scaled(pts, ref)
        if gain is None:
            continue
        reaches_back = pts[0][0] <= ref - timedelta(days=2 * WINDOW_DAYS)
        prev = _scaled(pts, ref - timedelta(days=WINDOW_DAYS)) if reaches_back else None
        shop_id, tags = products[pid]
        out.append(ListingGain(pid, shop_id, tuple(str(t) for t in tags), gain, prev))
    return out


def compute_topics(session: Session, today: date, cfg: TopicsConfig | None = None) -> list[TopicSnapshot]:
    """Replace today's topic rows with a fresh build."""
    cfg = cfg or load_topics_config()
    topics = build_topics(listing_gains(session), cfg)
    session.execute(delete(TopicSnapshot).where(TopicSnapshot.date == today))
    index = ip_index(session)
    rows = [
        TopicSnapshot(
            date=today, key=t.key, rank=rank, aliases=list(t.aliases), listings=t.listings, shops=t.shops,
            rising=t.rising, gain_7d=round(t.gain_7d, 2),
            prev_gain_7d=round(t.prev_gain_7d, 2) if t.prev_gain_7d is not None else None,
            score=round(t.score, 4), product_ids=list(t.product_ids[:8]), ip_level=index.check(t.key)["level"],
        )
        for rank, t in enumerate(topics, start=1)
    ]
    session.add_all(rows)
    session.flush()
    return rows


def latest_topics(session: Session, cfg: TopicsConfig | None = None) -> dict:
    """The newest scan date's topics with `new` flags, score series and sample products."""
    cfg = cfg or load_topics_config()
    latest = session.scalar(select(func.max(TopicSnapshot.date)))
    if latest is None:
        return {"date": None, "items": []}
    rows = list(session.scalars(select(TopicSnapshot).where(TopicSnapshot.date == latest).order_by(TopicSnapshot.rank)))
    keys = [r.key for r in rows]
    since = latest - timedelta(days=cfg.new_lookback_days)
    earlier = set(session.scalars(
        select(TopicSnapshot.key).where(TopicSnapshot.date >= since, TopicSnapshot.date < latest).distinct()
    ))
    has_history = session.scalar(select(func.min(TopicSnapshot.date))) < latest
    series: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for key, d, score in session.execute(
        select(TopicSnapshot.key, TopicSnapshot.date, TopicSnapshot.score)
        .where(TopicSnapshot.key.in_(keys), TopicSnapshot.date > latest - timedelta(days=SERIES_DAYS))
        .order_by(TopicSnapshot.date)
    ):
        series[key].append((d, score))
    wanted = {pid for r in rows for pid in (r.product_ids or [])[:SAMPLE_PRODUCTS]}
    products = {
        p.id: p for p in session.scalars(select(Product).where(Product.id.in_(wanted)))
    } if wanted else {}
    items = []
    for r in rows:
        growth = r.gain_7d / r.prev_gain_7d - 1 if r.prev_gain_7d else None
        items.append({
            "key": r.key, "rank": r.rank, "aliases": r.aliases or [], "listings": r.listings, "shops": r.shops,
            "rising": r.rising, "gain_7d": r.gain_7d, "prev_gain_7d": r.prev_gain_7d, "growth": growth,
            "score": r.score, "ip_level": r.ip_level,
            "new": has_history and r.key not in earlier,
            "series": [{"date": d, "score": s} for d, s in series[r.key]],
            "products": [
                {"id": p.id, "title": p.title, "url": p.url, "image_url": p.image_url}
                for pid in (r.product_ids or [])[:SAMPLE_PRODUCTS] if (p := products.get(pid)) is not None
            ],
        })
    return {"date": latest, "items": items}
