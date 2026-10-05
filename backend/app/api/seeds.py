from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import SeedIn, SeedOut
from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import Seed

router = APIRouter(prefix="/api")


def _to_out(session: Session, seed: Seed) -> SeedOut:
    keyword = get_or_create_keyword(session, seed.keyword)
    return SeedOut(
        id=seed.id,
        keyword=seed.keyword,
        active=seed.active,
        created_at=seed.created_at,
        keyword_id=keyword.id,
    )


@router.get("/seeds", response_model=list[SeedOut])
def list_seeds(session: Session = Depends(get_session)) -> list[SeedOut]:
    seeds = session.scalars(select(Seed).order_by(Seed.id)).all()
    out = [_to_out(session, s) for s in seeds]
    session.commit()  # persists keywords created for legacy seeds
    return out


@router.post("/seeds", response_model=SeedOut, status_code=201)
def create_seed(body: SeedIn, session: Session = Depends(get_session)) -> SeedOut:
    text = normalize_keyword(body.keyword)
    if session.scalar(select(Seed).where(Seed.keyword == text)) is not None:
        raise HTTPException(status_code=409, detail="Seed already exists")
    seed = Seed(keyword=text)
    session.add(seed)
    session.flush()
    out = _to_out(session, seed)
    session.commit()
    return out


@router.delete("/seeds/{seed_id}", status_code=204)
def delete_seed(seed_id: int, session: Session = Depends(get_session)) -> Response:
    seed = session.get(Seed, seed_id)
    if seed is None:
        raise HTTPException(status_code=404, detail="Seed not found")
    session.delete(seed)
    session.commit()
    return Response(status_code=204)
