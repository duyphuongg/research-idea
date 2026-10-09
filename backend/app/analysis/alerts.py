"""Alert rules: which niches/products are worth telling the user about after a scan."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

from app.config_files import load_yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AlertsConfig:
    niche_min_score: float = 60
    niche_min_growth: float = 0.20
    cooldown_days: int = 7
    telegram_max_items: int = 5
    quiet_start: int = 22  # local hour; no Telegram from quiet_start until quiet_end (equal = off)
    quiet_end: int = 7
    shop_min_sales_7d: int = 30  # 🏪 watched shop: orders in the last 7 days …
    shop_growth: float = 1.5  # … and at least this multiple of the previous week (when known)
    nfl_min_potential: float = 85  # 🏈 NFL player: shirt potential (0–100) of the latest full week
    nfl_max_per_week: int = 3  # at most this many players per game week
    nfl_moment_min_traffic: int = 20000  # 🗯️ NFL trending search: approx Google searches …
    nfl_moment_max_per_day: int = 2  # … at most this many per day


def load_alerts_config() -> AlertsConfig:
    data = load_yaml("alerts.yaml")
    kwargs = {}
    for f in fields(AlertsConfig):
        if f.name in data:
            kwargs[f.name] = int(data[f.name]) if f.type in (int, "int") else float(data[f.name])
    for name in ("quiet_start", "quiet_end"):
        if name in kwargs and not 0 <= kwargs[name] <= 23:
            logger.warning("alerts.yaml: %s=%s is outside 0-23, using the default %s",
                           name, kwargs[name], getattr(AlertsConfig, name))
            del kwargs[name]
    return AlertsConfig(**kwargs)


LISTING_LABEL = {"super_breakout": "Super Breakout", "steady_grower": "Steady Grower"}
METRIC_LABEL = {"reviews": "reviews", "favorites": "lượt lưu", "views": "lượt xem"}
# Telegram order: super breakout, niche, steady grower, shop, hot product (unknown kinds last)
KIND_RANK = {("listing", 2): 0, ("nfl_moment", 1): 1, ("nfl", 1): 1, ("niche", 1): 2, ("listing", 1): 3, ("shop", 1): 4,
             ("hot_product", 1): 5}


@dataclass(frozen=True)
class AlertCandidate:
    kind: str
    subject_id: int
    level: int
    priority: float
    title: str
    reason: str
    image_url: str | None
    link: str
    external_url: str | None
    watch_keyword: str | None


@dataclass(frozen=True)
class NicheRow:
    keyword_id: int
    text: str
    score: float
    growth: float | None
    watch_keyword: str


@dataclass(frozen=True)
class ListingRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    status: str
    delta_saves: float | None
    dsr: float | None
    watch_keyword: str | None
    link: str


@dataclass(frozen=True)
class HotRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    velocity: float | None
    metric: str | None
    watch_keyword: str
    link: str


@dataclass(frozen=True)
class ShopRow:
    shop_id: int
    name: str
    url: str | None
    icon_url: str | None
    sales_7d: int
    days_7d: int  # actual span the 7-day sales cover
    prev_sales_7d: int | None
    prev_days_7d: int = 7  # actual span the previous-week value covers


@dataclass(frozen=True)
class NflRow:
    athlete_id: str
    name: str
    team: str | None
    position: str | None
    potential: float
    stat_lines: list[str]
    etsy_listings: int | None
    trending: bool
    headshot_url: str | None
    week: int


@dataclass(frozen=True)
class PastAlert:
    kind: str
    subject_id: int
    level: int
    created_at: datetime


def niche_candidates(rows: Iterable[NicheRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    return [
        AlertCandidate(
            kind="niche", subject_id=r.keyword_id, level=1, priority=r.score, title=r.text,
            reason=f"Điểm {r.score:.0f} · tăng {r.growth * 100:.0f}%", image_url=None,
            link=f"/trends/{r.keyword_id}", external_url=None, watch_keyword=r.watch_keyword,
        )
        for r in rows
        if r.score >= cfg.niche_min_score and r.growth is not None and r.growth > cfg.niche_min_growth
    ]


def listing_candidates(rows: Iterable[ListingRow]) -> list[AlertCandidate]:
    out = []
    for r in rows:
        if r.status == "super_breakout":
            level = 2
        elif r.status == "steady_grower" and r.watch_keyword is not None:
            level = 1
        else:
            continue
        parts = [LISTING_LABEL[r.status]]
        if r.delta_saves is not None:
            parts.append(f"+{r.delta_saves:.0f} lượt lưu/ngày")
        if r.dsr is not None:
            parts.append(f"DSR {r.dsr * 100:.0f}%")
        out.append(AlertCandidate(
            kind="listing", subject_id=r.product_id, level=level, priority=r.delta_saves or 0.0,
            title=r.title, reason=" · ".join(parts), image_url=r.image_url, link=r.link,
            external_url=r.url, watch_keyword=r.watch_keyword,
        ))
    return out


def hot_candidates(rows: Iterable[HotRow]) -> list[AlertCandidate]:
    out = []
    for r in rows:
        reason = "Đang bán chạy"
        if r.velocity is not None and r.metric:
            reason += f" · +{r.velocity:.1f} {METRIC_LABEL.get(r.metric, r.metric)}/tuần"
        out.append(AlertCandidate(
            kind="hot_product", subject_id=r.product_id, level=1, priority=r.velocity or 0.0,
            title=r.title, reason=reason, image_url=r.image_url, link=r.link,
            external_url=r.url, watch_keyword=r.watch_keyword,
        ))
    return out


def shop_candidates(rows: Iterable[ShopRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    out = []
    for r in rows:
        if not 7 <= r.days_7d <= 9 or r.sales_7d < cfg.shop_min_sales_7d:
            continue
        prev = None
        if r.prev_sales_7d is not None and r.prev_days_7d >= 3:  # shorter spans are too noisy to scale
            prev = round(r.prev_sales_7d * 7 / r.prev_days_7d)
        if prev is not None and r.sales_7d < cfg.shop_growth * max(prev, 1):
            continue
        reason = f"+{r.sales_7d} đơn/7 ngày"
        if prev is not None:
            reason += f" (tuần trước +{prev})"
        out.append(AlertCandidate(
            kind="shop", subject_id=r.shop_id, level=1, priority=float(r.sales_7d), title=r.name,
            reason=reason, image_url=r.icon_url, link=f"/shops/{r.shop_id}", external_url=r.url,
            watch_keyword=None,
        ))
    return out


def nfl_candidates(rows: Iterable[NflRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    out = []
    for r in sorted(rows, key=lambda r: -r.potential):
        if r.potential < cfg.nfl_min_potential or len(out) >= cfg.nfl_max_per_week:
            break
        if not r.athlete_id.isdigit():
            continue
        tags = " · ".join(t for t in (r.team, r.position) if t)
        parts = [f"Tuần {r.week}", *r.stat_lines, f"tiềm năng {r.potential:.0f}"]
        if r.etsy_listings is not None:
            parts.append(f"Etsy {r.etsy_listings} listing")
        if r.trending:
            parts.append("🔥 đang trend")
        out.append(AlertCandidate(
            kind="nfl", subject_id=int(r.athlete_id), level=1, priority=r.potential,
            title=f"{r.name} ({tags})" if tags else r.name, reason=" · ".join(parts),
            image_url=r.headshot_url, link="/nfl", external_url=None, watch_keyword=None,
        ))
    return out


@dataclass(frozen=True)
class MomentRow:
    moment_id: int
    query: str
    traffic: int
    news_title: str | None
    news_url: str | None
    image_url: str | None
    player: str | None  # "WSH · QB Jayden Daniels"


def moment_candidates(rows: Iterable[MomentRow], cfg: AlertsConfig, left_today: int) -> list[AlertCandidate]:
    out = []
    for r in sorted(rows, key=lambda r: (-r.traffic, r.moment_id)):
        if r.traffic < cfg.nfl_moment_min_traffic or len(out) >= left_today:
            break
        parts = [f"{r.traffic:,}+ lượt tìm".replace(",", ".")]
        if r.player:
            parts.append(r.player)
        if r.news_title:
            parts.append(r.news_title)
        out.append(AlertCandidate(
            kind="nfl_moment", subject_id=r.moment_id, level=1, priority=float(r.traffic), title=r.query,
            reason=" · ".join(parts)[:300], image_url=r.image_url, link="/nfl", external_url=r.news_url,
            watch_keyword=None,
        ))
    return out


def dedupe(
    cands: Iterable[AlertCandidate], past: Iterable[PastAlert], now: datetime, cooldown_days: int
) -> list[AlertCandidate]:
    """Drop candidates alerted within the cooldown unless the level rose; one per (kind, subject)."""
    cutoff = now - timedelta(days=cooldown_days)
    recent: dict[tuple[str, int], int] = {}
    for p in past:
        if p.created_at >= cutoff:
            key = (p.kind, p.subject_id)
            recent[key] = max(recent.get(key, 0), p.level)
    best: dict[tuple[str, int], AlertCandidate] = {}
    for c in cands:
        key = (c.kind, c.subject_id)
        if key in recent and c.level <= recent[key]:
            continue
        if key not in best or c.level > best[key].level:
            best[key] = c
    return list(best.values())


def telegram_order(kind: str, level: int, priority: float) -> tuple[int, float]:
    return (KIND_RANK.get((kind, level), 9), -priority)
