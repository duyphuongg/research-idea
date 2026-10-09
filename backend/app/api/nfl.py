from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import NflPage
from app.services.nfl import standouts

router = APIRouter(prefix="/api")


@router.get("/nfl/standouts", response_model=NflPage)
def nfl_standouts(
    season: int | None = None,
    season_type: int | None = Query(None, ge=1, le=4),
    week: int | None = Query(None, ge=1, le=30),
    session: Session = Depends(get_session),
):
    return standouts(session, season, season_type, week)
