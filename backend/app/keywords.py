from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Keyword


def normalize_keyword(text: str) -> str:
    return " ".join(text.lower().split())


def get_or_create_keyword(session: Session, text: str, origin: str = "seed") -> Keyword:
    norm = normalize_keyword(text)
    keyword = session.scalar(select(Keyword).where(Keyword.text == norm))
    if keyword is None:
        keyword = Keyword(text=norm, origin=origin)
        session.add(keyword)
        session.flush()
    return keyword
