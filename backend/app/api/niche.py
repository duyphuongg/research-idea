from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import NicheReport
from app.services.niche import niche_report

router = APIRouter(prefix="/api")


@router.get("/niche", response_model=NicheReport)
def niche(
    keyword: str = Query(..., max_length=200),
    product_type: Literal["tshirt", "sweatshirt", "hoodie"] | None = None,
    session: Session = Depends(get_session),
):
    if not keyword.strip():
        raise HTTPException(status_code=422, detail="keyword is empty")
    return niche_report(session, keyword, product_type)
