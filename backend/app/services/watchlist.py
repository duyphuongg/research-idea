"""Watchlist (seed keywords) helpers shared by the Watchlist page, Signals filter and alerts."""

import re

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import Session

from app.keywords import canonical_keyword, normalize_keyword
from app.models import Keyword, KeywordRelation, ListingSignal, Product, Seed


def watch_keywords(session: Session) -> list[Seed]:
    return list(session.scalars(select(Seed).where(Seed.active.is_(True)).order_by(Seed.id)))


_EDGE_L, _EDGE_R = r"(?<![a-zA-Z0-9])", r"(?![a-zA-Z0-9])"


def keyword_regex(keyword: str) -> str:
    """Whole-word pattern for a watch keyword: words joined by space/hyphen, optional plural 's'.

    Uses alphanumeric lookarounds rather than \\b, which fails next to punctuation such as '%'.
    """
    words = [re.escape(w) for w in normalize_keyword(keyword).split()]
    if not words:
        return r"(?!)"
    return _EDGE_L + r"[\s\-]+".join(words) + r"s?" + _EDGE_R


def listing_keyword_filter(keyword: str, suffix: str) -> ColumnElement[bool]:
    """Listing found by '<keyword> <suffix>' or whose title contains the keyword as a whole word."""
    kw = normalize_keyword(keyword)
    return or_(
        ListingSignal.discovery_query == f"{kw} {suffix}",
        Product.title.regexp_match("(?i)" + keyword_regex(keyword)),
    )


def listing_matches(keyword: str, discovery_query: str, title: str, suffix: str) -> bool:
    kw = normalize_keyword(keyword)
    return discovery_query == f"{kw} {suffix}" or bool(re.search(keyword_regex(keyword), title, re.IGNORECASE))


def seed_keyword_ids(session: Session, seed_text: str) -> list[int]:
    """Keyword ids for a seed (its normalized and canonical forms), the normalized form first."""
    norm = normalize_keyword(seed_text)
    texts = {norm, canonical_keyword(seed_text)}
    return list(session.scalars(
        select(Keyword.id).where(Keyword.text.in_(texts)).order_by(Keyword.text != norm, Keyword.id)
    ))


def child_keyword_ids(session: Session, seed_text: str) -> list[int]:
    parent_ids = seed_keyword_ids(session, seed_text)
    if not parent_ids:
        return []
    return sorted(set(session.scalars(
        select(KeywordRelation.child_id).where(KeywordRelation.parent_id.in_(parent_ids))
    )))
