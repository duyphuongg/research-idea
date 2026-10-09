"""Detect alerts (niches, listings, watched shops, hot products) after a scan."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.alerts import (
    AlertCandidate, AlertsConfig, HotRow, ListingRow, MomentRow, NflRow, NicheRow, PastAlert, ShopRow,
    dedupe, hot_candidates, listing_candidates, load_alerts_config, moment_candidates, nfl_candidates, niche_candidates,
    shop_candidates,
)
from app.analysis.listing_signals import load_signals_config
from app.db import utcnow
from app.models import (
    Alert, Keyword, KeywordScore, ListingSignal, NflMoment, NflPerformance, NflPlayer, Product, ProductKeyword, Shop,
)
from app.services.hot import compute_product_metrics
from app.services.nfl import standouts
from app.services.shops import shop_metrics
from app.services.work import blocked_subjects
from app.services.watchlist import child_keyword_ids, listing_matches, seed_keyword_ids, watch_keywords


SUBJECT_KIND = {"niche": "keyword", "listing": "product", "hot_product": "product"}


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


NFL_FRESH_DAYS = 8  # only alert on a week whose last game is this recent


def _nfl_candidates(session: Session, now: datetime, cfg: AlertsConfig) -> list[AlertCandidate]:
    """Top players of the latest full week; at most cfg.nfl_max_per_week alerts per game week."""
    page = standouts(session, today=now.date())
    if page["week"] is None or not page["items"]:
        return []
    last_game = session.scalar(select(func.max(NflPerformance.game_date)).where(
        NflPerformance.season == page["season"], NflPerformance.season_type == page["season_type"],
        NflPerformance.week == page["week"]))
    if last_game is None or last_game < now - timedelta(days=NFL_FRESH_DAYS):
        return []
    # one alert per player per week (games are 7 days apart, so the usual cooldown would misfire)
    prefix = f"Tuần {page['week']} ·"
    done = set(session.scalars(select(Alert.subject_id).where(
        Alert.kind == "nfl", Alert.reason.startswith(prefix), Alert.created_at >= now - timedelta(days=60))))
    rows = [
        NflRow(i["athlete_id"], i["name"], i["team"], i["position"], i["potential"],
               [line["stat_line"] for line in i["lines"]], i["etsy_listings"], i["trending"],
               i["headshot_url"], page["week"])
        for i in page["items"]
        if not (i["athlete_id"].isdigit() and int(i["athlete_id"]) in done)
    ]
    left = max(0, cfg.nfl_max_per_week - len(done))
    return nfl_candidates(rows, replace(cfg, nfl_max_per_week=left))


MOMENT_FRESH_DAYS = 2


def _moment_candidates(session: Session, now: datetime, cfg: AlertsConfig) -> list[AlertCandidate]:
    """Big NFL trending searches first seen recently; each once, at most cfg.nfl_moment_max_per_day a day."""
    alerted = set(session.scalars(select(Alert.subject_id).where(Alert.kind == "nfl_moment")))
    day_start = now - timedelta(hours=24)
    sent_today = session.scalar(select(func.count()).select_from(Alert).where(
        Alert.kind == "nfl_moment", Alert.created_at >= day_start)) or 0
    left = max(0, cfg.nfl_moment_max_per_day - sent_today)
    if not left:
        return []
    rows = []
    for m in session.scalars(select(NflMoment).where(
        NflMoment.first_seen >= now - timedelta(days=MOMENT_FRESH_DAYS),
        NflMoment.traffic >= cfg.nfl_moment_min_traffic,
    )):
        if m.id in alerted:
            continue
        player = session.get(NflPlayer, m.athlete_id) if m.athlete_id else None
        label = " · ".join(x for x in (player.team, player.position) if x) + f" {player.name}" if player else m.team
        news = (m.news or [{}])[0] if m.news else {}
        rows.append(MomentRow(m.id, m.query, m.traffic, news.get("title"), news.get("url"),
                              m.picture_url or (player.headshot_url if player else None), label))
    return moment_candidates(rows, cfg, left)


def detect_moment_alerts(session: Session, now: datetime | None = None, cfg: AlertsConfig | None = None) -> list[Alert]:
    """Only the 🗯️ NFL moment alerts (the hourly job); detect_alerts includes them too."""
    cfg = cfg or load_alerts_config()
    now = now or utcnow()
    alerts = [_to_alert(c, now.date(), now) for c in _moment_candidates(session, now, cfg)]
    session.add_all(alerts)
    session.flush()
    return alerts


def _to_alert(c: AlertCandidate, today: date, now: datetime) -> Alert:
    return Alert(
        kind=c.kind, subject_id=c.subject_id, level=c.level, priority=c.priority, title=c.title[:300],
        reason=c.reason, image_url=c.image_url, link=c.link, external_url=c.external_url,
        watch_keyword=c.watch_keyword, scan_date=today, created_at=now,
    )


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
        *_nfl_candidates(session, now, cfg),
        *_moment_candidates(session, now, cfg),
    ]
    blocked = blocked_subjects(session)  # the user marked these listed/skipped
    cands = [c for c in cands if (SUBJECT_KIND.get(c.kind), c.subject_id) not in blocked]
    past = [
        PastAlert(a.kind, a.subject_id, a.level, a.created_at)
        for a in session.scalars(select(Alert).where(
            Alert.created_at >= now - timedelta(days=cfg.cooldown_days), Alert.kind.not_in(("nfl", "nfl_moment"))))
    ]
    alerts = [_to_alert(c, today, now) for c in dedupe(cands, past, now, cfg.cooldown_days)]
    session.add_all(alerts)
    session.flush()
    return alerts
