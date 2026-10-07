"""Alert rules: which niches/products are worth telling the user about after a scan."""

from collections.abc import Iterable
from dataclasses import dataclass, fields
from datetime import datetime, timedelta

from app.config_files import load_yaml


@dataclass(frozen=True)
class AlertsConfig:
    niche_min_score: float = 60
    niche_min_growth: float = 0.20
    amazon_top_n: int = 20
    cooldown_days: int = 7
    telegram_max_items: int = 5
    quiet_start: int = 22  # local hour; no Telegram from quiet_start until quiet_end (equal = off)
    quiet_end: int = 7


def load_alerts_config() -> AlertsConfig:
    data = load_yaml("alerts.yaml")
    kwargs = {}
    for f in fields(AlertsConfig):
        if f.name in data:
            kwargs[f.name] = int(data[f.name]) if f.type in (int, "int") else float(data[f.name])
    return AlertsConfig(**kwargs)


AMAZON_CATEGORY_LABEL = {
    "women_tshirts": "Áo thun nữ", "men_tshirts": "Áo thun nam", "women_hoodies": "Hoodie nữ",
    "women_sweatshirts": "Sweatshirt nữ", "men_hoodies": "Hoodie nam", "men_sweatshirts": "Sweatshirt nam",
    "boys_tops": "Áo bé trai", "girls_tops": "Áo bé gái",
}
LISTING_LABEL = {"super_breakout": "Super Breakout", "steady_grower": "Steady Grower"}
METRIC_LABEL = {"reviews": "reviews", "favorites": "lượt lưu", "views": "lượt xem"}
# Telegram order: super breakout, niche, amazon, steady grower, hot product
KIND_RANK = {("listing", 2): 0, ("niche", 1): 1, ("amazon", 1): 2, ("listing", 1): 3, ("hot_product", 1): 4}


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
class AmazonRow:
    product_id: int
    title: str
    url: str
    image_url: str | None
    category_key: str
    rank: int
    was_in_top: bool


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


def amazon_candidates(rows: Iterable[AmazonRow], cfg: AlertsConfig) -> list[AlertCandidate]:
    return [
        AlertCandidate(
            kind="amazon", subject_id=r.product_id, level=1, priority=-float(r.rank), title=r.title,
            reason=f"Hạng {r.rank} · {AMAZON_CATEGORY_LABEL.get(r.category_key, r.category_key)} · Best Sellers",
            image_url=r.image_url, link=f"/amazon?category={r.category_key}",
            external_url=r.url, watch_keyword=None,
        )
        for r in rows
        if r.rank <= cfg.amazon_top_n and not r.was_in_top
    ]


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
