"""Niche research: Etsy competition, price reference, top tags and a 13-tag set for one keyword."""

from datetime import date, timedelta
from statistics import median

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.analysis.listing_signals import BREAKOUT_STATUSES
from app.keywords import canonical_keyword, normalize_keyword
from app.models import KeywordScore, ListingSignal, Product, ProductKeyword, ProductSnapshot, TrendSignal
from app.services.ip import ip_index
from app.services.watchlist import keyword_regex, seed_keyword_ids

PRODUCT_TYPES = ("tshirt", "sweatshirt", "hoodie")
FRESH_DAYS = 30  # products seen in a scan within this many days
LOW_COMPETITION, HIGH_COMPETITION = 10_000, 50_000  # Etsy results for "<kw> shirt"
COMPETITION_DAYS = 7
MAX_TAGS = 60
ETSY_TAGS, ETSY_TAG_CHARS = 13, 20
TITLE_PHRASES = 6
RISING_LIFT, RISING_MIN_BREAKOUTS = 1.5, 2
HOT_STATUSES = (*BREAKOUT_STATUSES, "graduated")  # breaking out now, or proven sellers


def competition_level(tshirt_count: float | None) -> str | None:
    if tshirt_count is None:
        return None
    if tshirt_count < LOW_COMPETITION:
        return "low"
    return "medium" if tshirt_count < HIGH_COMPETITION else "high"


def opportunity(score: KeywordScore) -> float | None:
    """Hot and uncrowded: mean(demand, momentum) scaled by how little competition there is."""
    if score.competition is None:
        return None
    heat = ((score.demand or 0.0) + (0.5 if score.momentum is None else score.momentum)) / 2
    return round(100 * heat * (1 - score.competition), 1)


def percentile(values: list[float], q: float) -> float:
    """Linear interpolation between closest ranks (values need not be sorted)."""
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def competition(session: Session, keyword_ids: list[int], anchor: date | None = None) -> dict:
    """Latest Etsy result counts per product type (all from the same day)."""
    empty = {"date": None, "counts": {}, "level": None}
    if not keyword_ids:
        return empty
    query = select(func.max(TrendSignal.date)).where(
        TrendSignal.keyword_id.in_(keyword_ids), TrendSignal.source == "etsy",
        TrendSignal.metric.like("listing_count_%"),
    )
    if anchor is not None:
        query = query.where(TrendSignal.date <= anchor, TrendSignal.date > anchor - timedelta(days=COMPETITION_DAYS))
    day = session.scalar(query)
    if day is None:
        return empty
    counts: dict[str, int] = {}
    for metric, value in session.execute(
        select(TrendSignal.metric, TrendSignal.value).where(
            TrendSignal.keyword_id.in_(keyword_ids), TrendSignal.source == "etsy",
            TrendSignal.metric.like("listing_count_%"), TrendSignal.date == day,
        ).order_by(TrendSignal.keyword_id)
    ):
        counts.setdefault(metric.removeprefix("listing_count_"), int(value))
    counts = {t: counts[t] for t in PRODUCT_TYPES if t in counts}
    return {"date": day, "counts": counts, "level": competition_level(counts.get("tshirt"))}


def _niche_products(session: Session, keyword: str, keyword_ids: list[int], product_type: str | None):
    anchor = session.scalar(select(func.max(ProductSnapshot.date)))
    if anchor is None:
        return []
    matches = [Product.title.regexp_match("(?i)" + keyword_regex(keyword))]
    if keyword_ids:
        matches.append(Product.id.in_(
            select(ProductKeyword.product_id).where(ProductKeyword.keyword_id.in_(keyword_ids))
        ))
    types = (product_type,) if product_type else PRODUCT_TYPES
    rows = session.execute(
        select(Product, ListingSignal.status)
        .outerjoin(ListingSignal, ListingSignal.product_id == Product.id)
        .where(
            Product.source == "etsy", Product.product_type.in_(types), or_(*matches),
            exists().where(ProductSnapshot.product_id == Product.id,
                           ProductSnapshot.date >= anchor - timedelta(days=FRESH_DAYS)),
        )
        .order_by(Product.id)
    )
    return [(p, status in HOT_STATUSES) for p, status in rows]


def _price_row(product_type: str, rows: list[tuple[Product, bool]]) -> dict | None:
    prices = [p.price for p, _ in rows if p.price]
    if not prices:
        return None
    hot = [p.price for p, b in rows if b and p.price]
    return {
        "product_type": product_type, "count": len(prices),
        "p25": round(percentile(prices, 0.25), 2), "median": round(median(prices), 2),
        "p75": round(percentile(prices, 0.75), 2),
        "breakout_median": round(median(hot), 2) if hot else None,
    }


def generate_tags(keyword: str, rows: list[dict]) -> tuple[list[str], list[str]]:
    """13 Etsy tags (<= 20 chars, no singular/plural twins) and multi-word title phrases."""
    ranked = sorted(rows, key=lambda r: (-(r["share"] + 2 * r["breakout_share"]), r["tag"]))
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        key = canonical_keyword(tag)
        if key not in seen and len(tag) <= ETSY_TAG_CHARS and len(tags) < ETSY_TAGS:
            seen.add(key)
            tags.append(tag)

    add(normalize_keyword(keyword))
    for row in ranked:
        add(row["tag"])
    phrases: list[str] = []
    phrase_seen: set[str] = set()
    for row in ranked:
        key = canonical_keyword(row["tag"])
        if " " in row["tag"] and key not in phrase_seen and len(phrases) < TITLE_PHRASES:
            phrase_seen.add(key)
            phrases.append(row["tag"])
    return tags, phrases


def niche_report(session: Session, keyword: str, product_type: str | None = None) -> dict:
    keyword = normalize_keyword(keyword)
    keyword_ids = seed_keyword_ids(session, keyword)
    products = _niche_products(session, keyword, keyword_ids, product_type)
    n, b = len(products), sum(1 for _, hot in products if hot)

    counts: dict[str, list[int]] = {}
    for p, hot in products:
        for tag in {normalize_keyword(t) for t in (p.tags or []) if t.strip()}:
            c = counts.setdefault(tag, [0, 0])
            c[0] += 1
            c[1] += hot
    tags = []
    for tag, (listings, breakouts) in counts.items():
        lift = ((breakouts + 1) / (b + 2)) / ((listings + 1) / (n + 2))
        tags.append({
            "tag": tag, "listings": listings, "breakouts": breakouts,
            "share": round(listings / n, 4), "lift": round(lift, 2),
            "rising": breakouts >= RISING_MIN_BREAKOUTS and lift >= RISING_LIFT,
            "breakout_share": breakouts / b if b else 0.0,
        })
    tags.sort(key=lambda t: (-t["listings"], -t["breakouts"], t["tag"]))
    index = ip_index(session)
    checks = {t["tag"]: index.check(t["tag"]) for t in tags}
    for t in tags:
        t["ip_level"] = checks[t["tag"]]["level"]
    safe = [t for t in tags if t["ip_level"] != "red"]
    generated, phrases = generate_tags(keyword, safe) if safe else ([], [])
    if index.check(keyword)["level"] == "red":  # the keyword itself (added first) can be a trademark
        generated = [g for g in generated if index.check(g)["level"] != "red"]
    would_pick = generate_tags(keyword, tags)[0] if tags else []  # what the set would be without the check
    removed = [{"tag": g, "term": checks[g]["hits"][0]["term"]}
               for g in would_pick if g in checks and checks[g]["level"] == "red"]

    prices = []
    for t in (product_type,) if product_type else PRODUCT_TYPES:
        row = _price_row(t, [r for r in products if r[0].product_type == t])
        if row:
            prices.append(row)
    if prices:
        prices.append(_price_row("all", products))

    return {
        "keyword": keyword, "keyword_id": keyword_ids[0] if keyword_ids else None,
        "product_type": product_type, "listings": n, "breakouts": b,
        "competition": competition(session, keyword_ids),
        "prices": prices,
        "tags": [{k: v for k, v in t.items() if k != "breakout_share"} for t in tags[:MAX_TAGS]],
        "generated": {
            "tags": generated, "title_phrases": phrases, "removed": removed,
            "ip": {g: index.check(g)["level"] for g in generated},
        },
    }
