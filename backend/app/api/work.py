from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import WorkIn, WorkOut, WorkStatus
from app.db import utcnow
from app.models import WorkItem
from app.services.work import describe, subject_exists

router = APIRouter(prefix="/api")
Kind = Literal["keyword", "product"]


def _find(session: Session, kind: str, subject_id: int) -> WorkItem | None:
    return session.scalar(
        select(WorkItem).where(WorkItem.subject_kind == kind, WorkItem.subject_id == subject_id)
    )


@router.get("/work", response_model=list[WorkOut])
def list_work(status: WorkStatus | None = None, session: Session = Depends(get_session)):
    query = select(WorkItem).order_by(WorkItem.updated_at.desc(), WorkItem.id.desc())
    if status is not None:
        query = query.where(WorkItem.status == status)
    return [describe(session, item) for item in session.scalars(query)]


@router.put("/work/{kind}/{subject_id}", response_model=WorkOut)
def put_work(kind: Kind, subject_id: int, body: WorkIn, session: Session = Depends(get_session)):
    if not subject_exists(session, kind, subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    item = _find(session, kind, subject_id)
    if item is None:
        item = WorkItem(subject_kind=kind, subject_id=subject_id, status=body.status)
        session.add(item)
    item.status, item.note, item.updated_at = body.status, body.note, utcnow()
    session.commit()
    return describe(session, item)


@router.delete("/work/{kind}/{subject_id}", status_code=204)
def delete_work(kind: Kind, subject_id: int, session: Session = Depends(get_session)) -> Response:
    item = _find(session, kind, subject_id)
    if item is not None:
        session.delete(item)
        session.commit()
    return Response(status_code=204)
