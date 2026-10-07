from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import AmazonRank, KeywordRelation, KeywordScore, Product, ProductSnapshot


def test_normalize_keyword_lowercases_and_collapses_spaces():
    assert normalize_keyword("  Dog   MOM ") == "dog mom"


def test_get_or_create_keyword_is_idempotent(session):
    a = get_or_create_keyword(session, "Dog Mom")
    b = get_or_create_keyword(session, "dog  mom")
    assert a.id == b.id
    assert a.text == "dog mom"
    assert a.origin == "seed"


def test_product_snapshots_ordered_by_date(session):
    p = Product(source="etsy", external_id="1", title="T", url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add_all(
        [
            ProductSnapshot(product_id=p.id, date=date(2026, 9, 27), favorites=2),
            ProductSnapshot(product_id=p.id, date=date(2026, 9, 20), favorites=1),
        ]
    )
    session.commit()
    session.refresh(p)
    assert [s.date for s in p.snapshots] == [date(2026, 9, 20), date(2026, 9, 27)]


def test_product_unique_per_source_external_id(session):
    session.add(Product(source="etsy", external_id="1", title="A", url="u", product_type="tshirt"))
    session.add(Product(source="etsy", external_id="1", title="B", url="u", product_type="tshirt"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_snapshot_views_and_shop_sold_count(session):
    p = Product(source="etsy", external_id="9", title="T", url="u", product_type="tshirt", shop_sold_count=1500)
    session.add(p)
    session.flush()
    session.add(ProductSnapshot(product_id=p.id, date=date(2026, 10, 5), views=321))
    session.commit()
    session.refresh(p)
    assert p.shop_sold_count == 1500
    assert p.snapshots[0].views == 321


def test_keyword_relation_and_score(session):
    parent = get_or_create_keyword(session, "nurse")
    child = get_or_create_keyword(session, "nurse gift", origin="discovered")
    session.add(KeywordRelation(parent_id=parent.id, child_id=child.id, source="etsy_tags", last_seen=date(2026, 10, 5)))
    session.add(
        KeywordScore(
            keyword_id=child.id, date=date(2026, 10, 5), score=71.5, demand=0.8, momentum=None,
            competition=None, growth=None, sources_rising=0, sources=["etsy_tags"],
        )
    )
    session.commit()
    score = session.scalar(select(KeywordScore))
    assert (score.score, score.sources, score.momentum) == (71.5, ["etsy_tags"], None)
    assert session.get(KeywordRelation, (parent.id, child.id, "etsy_tags")) is not None


def test_keyword_score_unique_per_day(session):
    kw = get_or_create_keyword(session, "nurse")
    for _ in range(2):
        session.add(KeywordScore(keyword_id=kw.id, date=date(2026, 10, 5), score=1.0, sources_rising=0, sources=[]))
    with pytest.raises(IntegrityError):
        session.commit()


from app.models import ListingSignal  # noqa: E402


def test_listing_signal_row_and_product_tags(session):
    p = Product(source="etsy", external_id="77", title="T", url="u", product_type="tshirt", tags=["a", "b"])
    session.add(p)
    session.flush()
    session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 10, 6), discovery_query="shirt"))
    session.commit()
    row = session.get(ListingSignal, p.id)
    assert (row.status, row.discovery_query, row.dsr) == ("calibrating", "shirt", None)
    assert session.get(Product, p.id).tags == ["a", "b"]


def test_amazon_rank_unique_per_product_date_category_list(session):
    p = Product(source="amazon", external_id="B001", title="T", url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add(AmazonRank(product_id=p.id, date=date(2026, 10, 7), category_key="tshirt", list_name="bestsellers", rank=3))
    session.commit()
    session.add(AmazonRank(product_id=p.id, date=date(2026, 10, 7), category_key="tshirt", list_name="bestsellers", rank=4))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    assert p.licensed is None
