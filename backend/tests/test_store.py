from datetime import date

from sqlalchemy import func, select

from app.connectors.base import NormalizedBatch, NormalizedSignal
from app.models import Keyword, Product, ProductKeyword, ProductSnapshot, TrendSignal
from app.pipeline.store import persist_batch
from tests.fakes import make_product

D1 = date(2026, 9, 20)
D2 = date(2026, 9, 27)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_persists_new_product_with_keyword_and_snapshot(session):
    written = persist_batch(session, NormalizedBatch(products=[make_product(rank=4)]), D1)
    session.commit()

    assert written == 1
    product = session.scalar(select(Product))
    assert (product.source, product.external_id, product.title) == ("fake", "1", "Nurse Shirt")
    keyword = session.scalar(select(Keyword))
    assert keyword.text == "nurse"
    link = session.get(ProductKeyword, (product.id, keyword.id))
    assert (link.rank, link.last_seen) == (4, D1)
    snapshot = session.scalar(select(ProductSnapshot))
    assert (snapshot.date, snapshot.favorites, snapshot.price) == (D1, 10, 19.99)


def test_same_day_is_upserted_and_keeps_best_rank(session):
    batch = NormalizedBatch(
        products=[make_product(rank=5, favorites=10), make_product(rank=2, favorites=12)]
    )
    persist_batch(session, batch, D1)
    session.commit()

    assert count(session, Product) == 1
    assert count(session, ProductSnapshot) == 1
    assert session.scalar(select(ProductSnapshot)).favorites == 12
    assert session.scalar(select(ProductKeyword)).rank == 2


def test_next_day_adds_snapshot_and_updates_fields(session):
    persist_batch(session, NormalizedBatch(products=[make_product(favorites=10)]), D1)
    persist_batch(
        session, NormalizedBatch(products=[make_product(favorites=30, title="New Title", rank=9)]), D2
    )
    session.commit()

    assert count(session, ProductSnapshot) == 2
    assert session.scalar(select(Product)).title == "New Title"
    assert session.scalar(select(ProductKeyword)).rank == 9


def test_signals_are_upserted_per_day(session):
    sig = NormalizedSignal(keyword="Nurse", source="etsy", metric="listing_count_tshirt", value=1.0, date=D1)
    persist_batch(session, NormalizedBatch(signals=[sig]), D1)
    sig2 = NormalizedSignal(keyword="nurse", source="etsy", metric="listing_count_tshirt", value=2.0, date=D1)
    written = persist_batch(session, NormalizedBatch(signals=[sig2]), D1)
    session.commit()

    assert written == 1
    assert count(session, TrendSignal) == 1
    assert session.scalar(select(TrendSignal)).value == 2.0


from app.models import KeywordRelation  # noqa: E402


def test_discovered_signal_creates_child_keyword_and_relation(session):
    sig = NormalizedSignal(
        keyword="Funny Nurse Shirts", source="google_suggest", metric="suggest_score",
        value=9.0, date=D1, origin="discovered", parent="nurse",
    )
    persist_batch(session, NormalizedBatch(signals=[sig]), D1)
    session.commit()

    child = session.scalar(select(Keyword).where(Keyword.text == "funny nurse shirt"))
    parent = session.scalar(select(Keyword).where(Keyword.text == "nurse"))
    assert (child.origin, child.is_pod_relevant) == ("discovered", True)
    assert parent.origin == "seed"
    rel = session.get(KeywordRelation, (parent.id, child.id, "google_suggest"))
    assert rel.last_seen == D1


def test_discovered_keywords_get_pod_relevance(session):
    signals = [
        NormalizedSignal(keyword="nurse shirts near me", source="google_suggest", metric="suggest_score", value=5.0, date=D1, origin="discovered", parent="nurse"),
        NormalizedSignal(keyword="braves dodgers game", source="google_daily", metric="traffic", value=200.0, date=D1, origin="discovered"),
        NormalizedSignal(keyword="halloween costume ideas", source="google_daily", metric="traffic", value=50000.0, date=D1, origin="discovered"),
        NormalizedSignal(keyword="   ", source="google_daily", metric="traffic", value=1.0, date=D1, origin="discovered"),
    ]
    persist_batch(session, NormalizedBatch(signals=signals), D1)
    session.commit()

    relevance = {k.text: k.is_pod_relevant for k in session.scalars(select(Keyword))}
    assert relevance["nurse shirt near me"] is False
    assert relevance["brave dodger game"] is False
    assert relevance["halloween costume ideas"] is False
    assert "" not in relevance


def test_persists_views_and_shop_sold_count(session):
    persist_batch(session, NormalizedBatch(products=[make_product(views=420, shop_sold_count=9000)]), D1)
    session.commit()
    assert session.scalar(select(Product)).shop_sold_count == 9000
    assert session.scalar(select(ProductSnapshot)).views == 420


def test_seed_plus_product_word_signal_is_dropped(session):
    sigs = [
        NormalizedSignal(keyword="nurse shirts", source="google_suggest", metric="suggest_score", value=5.0, date=D1, origin="discovered", parent="nurse"),
        NormalizedSignal(keyword="nurse gift", source="google_suggest", metric="suggest_score", value=5.0, date=D1, origin="discovered", parent="nurse"),
    ]
    persist_batch(session, NormalizedBatch(signals=sigs), D1)
    session.commit()
    texts = {k.text for k in session.scalars(select(Keyword))}
    assert "nurse shirt" not in texts and "nurse shirts" not in texts
    assert "nurse gift" in texts
    assert count(session, KeywordRelation) == 1
    assert count(session, TrendSignal) == 1


from app.pipeline.store import upsert_product  # noqa: E402


def test_upsert_product_without_keyword_and_with_tags(session):
    product = upsert_product(session, make_product(keyword=None, tags=["vintage sasquatch"], views=10), D1)
    session.commit()
    assert product.tags == ["vintage sasquatch"]
    assert session.scalar(select(func.count()).select_from(ProductKeyword)) == 0
    assert session.scalar(select(ProductSnapshot)).views == 10
    upsert_product(session, make_product(keyword=None, tags=None), D2)
    session.commit()
    assert session.get(Product, product.id).tags == ["vintage sasquatch"]  # None keeps old tags
