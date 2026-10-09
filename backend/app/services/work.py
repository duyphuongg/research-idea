"""The user's own progress on niches and listings (Việc của tôi)."""

from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.listing_signals import load_signals_config
from app.models import Keyword, ListingSignal, Product, ProductKeyword, WorkItem

STATUSES = ("idea", "designing", "listed", "skipped")
KINDS = ("keyword", "product")
DONE = ("listed", "skipped")  # no more alerts for these


def niche_link(keyword: str) -> str:
    return "/niche?" + urlencode({"keyword": keyword})


def blocked_subjects(session: Session) -> set[tuple[str, int]]:
    """(kind, id) pairs the user marked listed or skipped."""
    return set(session.execute(
        select(WorkItem.subject_kind, WorkItem.subject_id).where(WorkItem.status.in_(DONE))
    ).all())


def subject_exists(session: Session, kind: str, subject_id: int) -> bool:
    return session.get(Keyword if kind == "keyword" else Product, subject_id) is not None


def _product_keyword(session: Session, product_id: int) -> str | None:
    text = session.scalar(
        select(Keyword.text).join(ProductKeyword, ProductKeyword.keyword_id == Keyword.id)
        .where(ProductKeyword.product_id == product_id).order_by(ProductKeyword.rank, Keyword.id).limit(1)
    )
    if text:
        return text
    query = session.scalar(select(ListingSignal.discovery_query).where(ListingSignal.product_id == product_id))
    suffix = " " + load_signals_config().seed_query_suffix
    if query and query.endswith(suffix):
        return query[: -len(suffix)]
    return query


def describe(session: Session, item: WorkItem) -> dict:
    out = {
        "subject_kind": item.subject_kind, "subject_id": item.subject_id, "status": item.status,
        "note": item.note, "updated_at": item.updated_at,
        "title": "", "image_url": None, "link": None, "external_url": None,
    }
    if item.subject_kind == "keyword":
        kw = session.get(Keyword, item.subject_id)
        if kw is not None:
            out.update(title=kw.text, link=niche_link(kw.text))
    else:
        p = session.get(Product, item.subject_id)
        if p is not None:
            keyword = _product_keyword(session, p.id)
            out.update(title=p.title, image_url=p.image_url, external_url=p.url,
                       link=niche_link(keyword) if keyword else None)
    return out
