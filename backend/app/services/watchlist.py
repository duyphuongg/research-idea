"""Watchlist (seed keywords) helpers shared by the Watchlist page, Signals filter and alerts."""

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.keywords import canonical_keyword, normalize_keyword
from app.models import Keyword, KeywordRelation, ListingSignal, Product, Seed


def watch_keywords(session: Session) -> list[Seed]:
    return list(session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)))


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def listing_keyword_filter(keyword: str, suffix: str) -> ColumnElement[bool]:
    """Listing found by '<keyword> <suffix>' or whose title contains the keyword (case-insensitive)."""
    kw = normalize_keyword(keyword)
    return or_(
        ListingSignal.discovery_query == f"{kw} {suffix}",
        func.lower(Product.title).like(f"%{_like_escape(kw)}%", escape="\\"),
    )


def listing_matches(keyword: str, discovery_query: str, title: str, suffix: str) -> bool:
    kw = normalize_keyword(keyword)
    return discovery_query == f"{kw} {suffix}" or kw in title.lower()


def child_keyword_ids(session: Session, seed_text: str) -> list[int]:
    texts = {normalize_keyword(seed_text), canonical_keyword(seed_text)}
    parent_ids = list(session.scalars(select(Keyword.id).where(Keyword.text.in_(texts))))
    if not parent_ids:
        return []
    return sorted(set(session.scalars(
        select(KeywordRelation.child_id).where(KeywordRelation.parent_id.in_(parent_ids))
    )))
