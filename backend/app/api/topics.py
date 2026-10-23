from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import TopicOut, TopicPage
from app.services.topics import latest_topics

router = APIRouter(prefix="/api")


@router.get("/topics", response_model=TopicPage)
def list_topics(
    sort: Literal["score", "growth", "new"] = "score",
    new_only: bool = False,
    hide_ip: bool = False,
    limit: int = Query(100, ge=1, le=200),
    session: Session = Depends(get_session),
) -> TopicPage:
    data = latest_topics(session)
    items = [TopicOut(**i) for i in data["items"]]
    items = [i for i in items if (not new_only or i.new) and not (hide_ip and i.ip_level == "red")]
    if sort == "growth":
        items.sort(key=lambda i: (i.growth is None, -(i.growth or 0), i.rank))
    elif sort == "new":
        items.sort(key=lambda i: (not i.new, i.rank))
    return TopicPage(date=data["date"], total=len(items), items=items[:limit])
