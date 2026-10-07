"""Detect alerts (niches, listings, hot products, Amazon entrants) after a scan."""

from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.alerts import (
    AlertCandidate, AlertsConfig, AmazonRow, HotRow, ListingRow, NicheRow, PastAlert,
    amazon_candidates, dedupe, hot_candidates, listing_candidates, load_alerts_config, niche_candidates,
)
from app.analysis.listing_signals import load_signals_config
from app.db import utcnow
from app.models import (
    Alert, AmazonRank, Keyword, KeywordScore, ListingSignal, Product, ProductKeyword,
)
from app.services.hot import compute_product_metrics
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


def _amazon_rows(session: Session, cfg: AlertsConfig) -> list[AmazonRow]:
    """Top-N rows of each category's latest bestsellers date, compared with that category's own previous
    date. A category with no previous date (new, or failed every earlier day) yields no rows, and a category
    whose latest date is older than the global latest (it failed the last scan) is skipped."""
    best = AmazonRank.list_name == "bestsellers"
    latest_by_cat = dict(session.execute(
        select(AmazonRank.category_key, func.max(AmazonRank.date)).where(best).group_by(AmazonRank.category_key)
    ).all())
    global_latest = max(latest_by_cat.values(), default=None)
    out = []
    for cat, latest in sorted(latest_by_cat.items()):
        if latest != global_latest:
            continue  # category failed the most recent scan: its data is stale
        in_cat = (best, AmazonRank.category_key == cat)
        prev = session.scalar(select(func.max(AmazonRank.date)).where(*in_cat, AmazonRank.date < latest))
        if prev is None:
            continue
        was_top = set(session.scalars(
            select(AmazonRank.product_id).where(*in_cat, AmazonRank.date == prev, AmazonRank.rank <= cfg.amazon_top_n)
        ))
        for r, p in session.execute(
            select(AmazonRank, Product)
            .join(Product, Product.id == AmazonRank.product_id)
            .where(*in_cat, AmazonRank.date == latest, AmazonRank.rank <= cfg.amazon_top_n,
                   Product.licensed.is_(False))
            .order_by(AmazonRank.rank)
        ):
            out.append(AmazonRow(p.id, p.title, p.url, p.image_url, cat, r.rank, r.product_id in was_top))
    return out


def detect_alerts(
    session: Session, today: date, cfg: AlertsConfig | None = None, now: datetime | None = None
) -> list[Alert]:
    cfg = cfg or load_alerts_config()
    now = now or utcnow()
    seeds = [s.keyword for s in watch_keywords(session)]

    cands: list[AlertCandidate] = [
        *niche_candidates(_niche_rows(session, seeds), cfg),
        *listing_candidates(_listing_rows(session, seeds)),
        *hot_candidates(_hot_rows(session, seeds)),
        *amazon_candidates(_amazon_rows(session, cfg), cfg),
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
