"""Ngách mới nổi: group listings into micro-niches by their tags and score each by saves velocity (pure)."""

import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, fields

from app.config_files import load_yaml
from app.keywords import canonical_keyword

MIN_KEY_CHARS = 3


@dataclass(frozen=True)
class TopicsConfig:
    min_listings: int = 5
    min_shops: int = 3
    max_top_share: float = 0.5
    merge_jaccard: float = 0.6
    prior_weight: float = 10
    rising_min_gain: float = 3
    max_topics: int = 100
    new_lookback_days: int = 7
    alert_top: int = 10
    alert_max: int = 3
    generic_words: frozenset[str] = field(default_factory=frozenset)


def load_topics_config() -> TopicsConfig:
    data = load_yaml("topics.yaml")
    kwargs: dict = {}
    for f in fields(TopicsConfig):
        if f.name == "generic_words" or f.name not in data:
            continue
        kwargs[f.name] = int(data[f.name]) if f.type in (int, "int") else float(data[f.name])
    words = {canonical_keyword(str(w)) for w in data.get("generic_words") or ()}
    return TopicsConfig(**kwargs, generic_words=frozenset(words))


@dataclass(frozen=True)
class ListingGain:
    product_id: int
    shop_id: int | None
    tags: tuple[str, ...]
    gain: float  # saves gained over the last 7 days (scaled to 7 days), never negative
    prev_gain: float | None  # the 7 days before that, when history reaches back


@dataclass(frozen=True)
class Topic:
    key: str
    aliases: tuple[str, ...]
    product_ids: tuple[int, ...]  # by gain, highest first
    shops: int
    rising: int
    gain_7d: float
    prev_gain_7d: float | None
    score: float  # Bayesian velocity relative to the population average (1.0 = average)

    @property
    def listings(self) -> int:
        return len(self.product_ids)

    @property
    def growth(self) -> float | None:
        if not self.prev_gain_7d:
            return None
        return self.gain_7d / self.prev_gain_7d - 1


def topic_key(tag: str, generic: frozenset[str]) -> str | None:
    """Canonical tag without generic words ("Black Cat Shirts" → "black cat"); None if nothing specific is left."""
    words = [w for w in canonical_keyword(tag).split() if w not in generic]
    key = " ".join(words)
    return key if len(key) >= MIN_KEY_CHARS else None


def build_topics(listings: Iterable[ListingGain], cfg: TopicsConfig) -> list[Topic]:
    """Topics ranked by score (highest first), at most cfg.max_topics."""
    rows = {r.product_id: r for r in listings}
    if not rows:
        return []
    log_gain = {pid: math.log1p(r.gain) for pid, r in rows.items()}
    mean = sum(log_gain.values()) / len(log_gain)
    if mean <= 0:
        return []

    members: dict[str, set[int]] = defaultdict(set)
    for r in rows.values():
        for key in {topic_key(t, cfg.generic_words) for t in r.tags} - {None}:
            members[key].add(r.product_id)

    def eligible(ids: set[int]) -> bool:
        if len(ids) < cfg.min_listings or len({rows[i].shop_id for i in ids}) < cfg.min_shops:
            return False
        total = sum(rows[i].gain for i in ids)
        return total > 0 and max(rows[i].gain for i in ids) <= cfg.max_top_share * total

    def score(ids: set[int]) -> float:
        k = cfg.prior_weight
        return (sum(log_gain[i] for i in ids) + k * mean) / (len(ids) + k) / mean

    candidates = sorted(
        ((key, ids) for key, ids in members.items() if eligible(ids)),
        key=lambda kv: (-score(kv[1]), -len(kv[1]), kv[0]),
    )
    kept: list[tuple[str, set[int], list[str]]] = []
    for key, ids in candidates:  # a near-duplicate of a better topic becomes its alias
        twin = next((t for t in kept if len(ids & t[1]) / len(ids | t[1]) >= cfg.merge_jaccard), None)
        if twin is not None:
            twin[2].append(key)
            continue
        kept.append((key, ids, []))
        if len(kept) >= cfg.max_topics:
            break

    out = []
    for key, ids, aliases in kept:
        prev = [rows[i].prev_gain for i in ids]
        out.append(Topic(
            key=key,
            aliases=tuple(aliases),
            product_ids=tuple(sorted(ids, key=lambda i: (-rows[i].gain, i))),
            shops=len({rows[i].shop_id for i in ids}),
            rising=sum(1 for i in ids if rows[i].gain >= cfg.rising_min_gain),
            gain_7d=sum(rows[i].gain for i in ids),
            prev_gain_7d=sum(p for p in prev if p is not None) if any(p is not None for p in prev) else None,
            score=score(ids),
        ))
    return out
