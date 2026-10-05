from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import adds_only_product_words
from app.connectors.base import NormalizedBatch, NormalizedProduct, NormalizedSignal
from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import KeywordRelation, Product, ProductKeyword, ProductSnapshot, TrendSignal


def persist_batch(session: Session, batch: NormalizedBatch, today: date) -> int:
    """Upsert signals, products, keyword links and today's snapshots. Does not commit."""
    for signal in batch.signals:
        _upsert_signal(session, signal)
    for item in batch.products:
        _upsert_product(session, item, today)
    session.flush()
    return len(batch.signals) + len(batch.products)


def _upsert_signal(session: Session, signal: NormalizedSignal) -> None:
    if not normalize_keyword(signal.keyword):
        return
    if signal.parent and adds_only_product_words(signal.keyword, signal.parent):
        return
    keyword = get_or_create_keyword(
        session, signal.keyword, signal.origin, has_parent=signal.parent is not None
    )
    if signal.parent:
        _upsert_relation(session, signal.parent, keyword.id, signal.source, signal.date)
    row = session.scalar(
        select(TrendSignal).where(
            TrendSignal.keyword_id == keyword.id,
            TrendSignal.source == signal.source,
            TrendSignal.metric == signal.metric,
            TrendSignal.date == signal.date,
        )
    )
    if row is None:
        session.add(
            TrendSignal(
                keyword_id=keyword.id,
                source=signal.source,
                metric=signal.metric,
                value=signal.value,
                date=signal.date,
            )
        )
    else:
        row.value = signal.value
    session.flush()


def _upsert_relation(
    session: Session, parent_text: str, child_id: int, source: str, seen: date
) -> None:
    parent = get_or_create_keyword(session, parent_text)
    if parent.id == child_id:
        return
    relation = session.get(KeywordRelation, (parent.id, child_id, source))
    if relation is None:
        session.add(
            KeywordRelation(parent_id=parent.id, child_id=child_id, source=source, last_seen=seen)
        )
    else:
        relation.last_seen = seen
    session.flush()


def _upsert_product(session: Session, item: NormalizedProduct, today: date) -> None:
    product = session.scalar(
        select(Product).where(Product.source == item.source, Product.external_id == item.external_id)
    )
    if product is None:
        product = Product(source=item.source, external_id=item.external_id)
        session.add(product)
    product.title = item.title
    product.url = item.url
    product.image_url = item.image_url
    product.shop_name = item.shop_name
    product.price = item.price
    product.currency = item.currency
    product.product_type = item.product_type
    product.listed_at = item.listed_at
    product.shop_sold_count = item.shop_sold_count
    session.flush()

    keyword = get_or_create_keyword(session, item.keyword)
    link = session.get(ProductKeyword, (product.id, keyword.id))
    if link is None:
        session.add(
            ProductKeyword(product_id=product.id, keyword_id=keyword.id, rank=item.rank, last_seen=today)
        )
    else:
        link.rank = min(link.rank, item.rank) if link.last_seen == today else item.rank
        link.last_seen = today

    snapshot = session.scalar(
        select(ProductSnapshot).where(
            ProductSnapshot.product_id == product.id, ProductSnapshot.date == today
        )
    )
    if snapshot is None:
        snapshot = ProductSnapshot(product_id=product.id, date=today)
        session.add(snapshot)
    snapshot.reviews = item.reviews
    snapshot.favorites = item.favorites
    snapshot.rating = item.rating
    snapshot.bsr = item.bsr
    snapshot.views = item.views
    snapshot.price = item.price
    session.flush()
