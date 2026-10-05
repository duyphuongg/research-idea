from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.pod_filter import is_pod_relevant
from app.models import Keyword


def normalize_keyword(text: str) -> str:
    return " ".join(text.lower().split())


def get_or_create_keyword(
    session: Session, text: str, origin: str = "seed", *, has_parent: bool = False
) -> Keyword:
    norm = normalize_keyword(text)
    keyword = session.scalar(select(Keyword).where(Keyword.text == norm))
    if keyword is None:
        keyword = Keyword(
            text=norm,
            origin=origin,
            is_pod_relevant=is_pod_relevant(norm, origin=origin, has_parent=has_parent),
        )
        session.add(keyword)
        session.flush()
    return keyword
