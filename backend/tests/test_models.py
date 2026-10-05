from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import Product, ProductSnapshot


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
