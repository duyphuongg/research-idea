"""Detect alerts (niches, listings, watched shops, hot products) after a scan."""

from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.alerts import (
    AlertCandidate, AlertsConfig, HotRow, ListingRow, NicheRow, PastAlert, ShopRow,
    dedupe, hot_candidates, listing_candidates, load_alerts_config, niche_candidates, shop_candidates,
)
from app.analysis.listing_signals import load_signals_config
from app.db import utcnow
from app.models import (
    Alert, Keyword, KeywordScore, ListingSignal, Product, ProductKeyword, Shop,
)
from app.services.hot import compute_product_metrics
from app.services.shops import shop_metrics
from app.services.watchlist import child_keyword_ids, listing_matches, seed_keyword_ids, watch_keywords


def _niche_rows(session: Session, seeds: list[str]) -> list[NicheRow]:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return []
    owner: dict[int, str] = {}
    for seed in seeds:
        for kid in seed_keyword_ids(session, seed) + child_keyword_ids(session, seed):
            owner.setdefault(kid, seed)
    if not owner:
        return []
    rows = session.execute(
        select(Keyword.id, Keyword.text, KeywordScore.score, KeywordScore.growth)
        .join(KeywordScore, KeywordScore.keyword_id == Keyword.id)
        .where(KeywordScore.date == latest, Keyword.id.in_(owner), Keyword.is_pod_relevant.is_(True))
        .order_by(Keyword.id)
    )
    return [NicheRow(kid, text, score, growth, owner[kid]) for kid, text, score, growth in rows]


def _listing_rows(session: Session, seeds: list[str]) -> list[ListingRow]:
    latest = session.scalar(select(func.max(ListingSignal.updated_on)))
    if latest is None:
        return []
    suffix = load_signals_config().seed_query_suffix
    out = []
    for sig, p in session.execute(
        select(ListingSignal, Product)
        .join(Product, Product.id == ListingSignal.product_id)
        .where(ListingSignal.updated_on == latest, ListingSignal.status.in_(("super_breakout", "steady_grower")))
        .order_by(ListingSignal.product_id)
    ):
        matched = next((s for s in seeds if listing_matches(s, sig.discovery_query, p.title, suffix)), None)
        link = (
            "/signals?" + urlencode({"keyword": matched, "status": "all"})
            if matched else "/signals?status=super_breakout"
        )
        out.append(ListingRow(p.id, p.title, p.url, p.image_url, sig.status, sig.delta_saves, sig.dsr, matched, link))
    return out


def _hot_rows(session: Session, seeds: list[str]) -> list[HotRow]:
    seed_by_kid: dict[int, str] = {}
    for seed in seeds:
        for kid in seed_keyword_ids(session, seed):
            seed_by_kid.setdefault(kid, seed)
    if not seed_by_kid:
        return []
    products, metrics = compute_product_metrics(session)
    links: dict[int, list[int]] = {}
    for pid, kid in session.execute(
        select(ProductKeyword.product_id, ProductKeyword.keyword_id).where(ProductKeyword.keyword_id.in_(seed_by_kid))
    ):
        links.setdefault(pid, []).append(kid)
    out = []
    for p in products:
        m = metrics[p.id]
        kids = links.get(p.id)
        if not m.hot or not kids:
            continue
        kid = min(kids)
        out.append(HotRow(p.id, p.title, p.url, p.image_url, m.velocity, m.metric, seed_by_kid[kid],
                          f"/products?keyword_id={kid}"))
    return out


def _shop_rows(session: Session) -> list[ShopRow]:
    """Watched shops with a known 7-day sales delta."""
    watched = list(session.scalars(select(Shop.id).where(Shop.watched_at.is_not(None))))
    if not watched:
        return []
    return [
        ShopRow(m.shop.id, m.shop.name, m.shop.url, m.shop.icon_url, m.sales_7d.value, m.sales_7d.days,
                m.prev_sales_7d.value if m.prev_sales_7d else None,
                m.prev_sales_7d.days if m.prev_sales_7d else 7)
        for m in shop_metrics(session, watched)
        if m.sales_7d is not None
    ]


def detect_alerts(
    session: Session, today: date, cfg: AlertsConfig | None = None, now: datetime | None = None
) -> list[Alert]:
    cfg = cfg or load_alerts_config()
    now = now or utcnow()
    seeds = [s.keyword for s in watch_keywords(session)]

    cands: list[AlertCandidate] = [
        *niche_candidates(_niche_rows(session, seeds), cfg),
        *listing_candidates(_listing_rows(session, seeds)),
        *shop_candidates(_shop_rows(session), cfg),
        *hot_candidates(_hot_rows(session, seeds)),
    ]
    past = [
        PastAlert(a.kind, a.subject_id, a.level, a.created_at)
        for a in session.scalars(select(Alert).where(Alert.created_at >= now - timedelta(days=cfg.cooldown_days)))
    ]
    alerts = [
        Alert(
            kind=c.kind, subject_id=c.subject_id, level=c.level, priority=c.priority, title=c.title[:300],
            reason=c.reason, image_url=c.image_url, link=c.link, external_url=c.external_url,
            watch_keyword=c.watch_keyword, scan_date=today, created_at=now,
        )
        for c in dedupe(cands, past, now, cfg.cooldown_days)
    ]
    session.add_all(alerts)
    session.flush()
    return alerts
