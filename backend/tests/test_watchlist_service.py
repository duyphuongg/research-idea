from datetime import date

import pytest
from sqlalchemy import select

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, ListingSignal, Product, Seed
from app.services.watchlist import child_keyword_ids, listing_keyword_filter, listing_matches, watch_keywords


def _listing(session, pid, title, query):
    p = Product(source="etsy", external_id=str(pid), title=title, url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 10, 1), discovery_query=query))
    return p


def test_listing_matches():
    assert listing_matches("Pickleball", "pickleball shirt", "x", "shirt")
    assert listing_matches("pickleball", "graphic tee", "Funny PICKLEBALL Tee", "shirt")
    assert not listing_matches("pickleball", "graphic tee", "tennis tee", "shirt")


MATCH_CASES = [
    ("nurse", "Funny Nurse Shirt", True),
    ("nurse", "Nurses Week Tee", True),
    ("nurse", "Nursery Rhyme Tee", False),
    ("game day", "Game-Day Football Tee", True),
    ("game day", "Endgame Dayton Tee", False),
    ("football mom", "Football Moms Club", True),
    ("100%", "Tennis 100% tee", True),
    ("100", "Tennis 1000 tee", False),
    ("pickleball", "PICKLEBALL Queen", True),
    ("", "Anything", False),
]


@pytest.mark.parametrize("keyword,title,expected", MATCH_CASES)
def test_whole_word_matching_python(keyword, title, expected):
    assert listing_matches(keyword, "graphic tee", title, "shirt") is expected


@pytest.mark.parametrize("keyword,title,expected", MATCH_CASES)
def test_whole_word_matching_sql(session, keyword, title, expected):
    p = _listing(session, 1, title, "graphic tee")
    session.flush()
    ids = session.scalars(
        select(Product.id).join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(listing_keyword_filter(keyword, "shirt"))
    ).all()
    assert (ids == [p.id]) is expected


def test_listing_keyword_filter_sql(session):
    a = _listing(session, 1, "Funny Pickleball Tee", "graphic tee")
    b = _listing(session, 2, "Anything", "pickleball shirt")
    _listing(session, 3, "Tennis 100% tee", "graphic tee")
    session.flush()
    ids = session.scalars(
        select(Product.id).join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(listing_keyword_filter("pickleball", "shirt"))
    ).all()
    assert sorted(ids) == sorted([a.id, b.id])
    # LIKE wildcards in the keyword are literal
    assert session.scalars(
        select(Product.id).join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(listing_keyword_filter("100%", "shirt"))
    ).all() == [3]


def test_watch_keywords_and_children(session):
    session.add_all([Seed(keyword="game day"), Seed(keyword="old", active=False)])
    parent = get_or_create_keyword(session, "game day")
    child = get_or_create_keyword(session, "game day vibes", origin="discovered", has_parent=True)
    session.add(KeywordRelation(parent_id=parent.id, child_id=child.id, source="etsy", last_seen=date(2026, 10, 7)))
    session.flush()
    assert [s.keyword for s in watch_keywords(session)] == ["game day"]
    assert child_keyword_ids(session, "game day") == [child.id]


def test_seed_keyword_ids_prefers_normalized_form(session):
    from app.keywords import get_or_create_keyword
    from app.services.watchlist import seed_keyword_ids

    assert seed_keyword_ids(session, "Game Days") == []
    canon = get_or_create_keyword(session, "game day")  # created first, so it has the lower id
    norm = get_or_create_keyword(session, "game days")
    assert seed_keyword_ids(session, "Game Days") == [norm.id, canon.id]
