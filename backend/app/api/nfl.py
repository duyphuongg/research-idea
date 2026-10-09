from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import NflMomentsPage, NflPage
from app.services.nfl import moments, standouts

router = APIRouter(prefix="/api")


@router.get("/nfl/standouts", response_model=NflPage)
def nfl_standouts(
    season: int | None = None,
    season_type: int | None = Query(None, ge=1, le=4),
    week: int | None = Query(None, ge=1, le=30),
    session: Session = Depends(get_session),
):
    return standouts(session, season, season_type, week)


@router.get("/nfl/moments", response_model=NflMomentsPage)
def nfl_moments(days: int = Query(7, ge=1, le=60), session: Session = Depends(get_session)):
    return {"items": moments(session, days)}
