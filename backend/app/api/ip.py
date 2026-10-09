from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import IpCheckIn, IpCheckOut
from app.services.ip import USPTO_URL, ip_index

router = APIRouter(prefix="/api")


@router.post("/ip/check", response_model=IpCheckOut)
def ip_check(body: IpCheckIn, session: Session = Depends(get_session)):
    index = ip_index(session)
    texts = [t.strip()[:300] for t in body.texts if t.strip()]
    return {"uspto_url": USPTO_URL, "results": [{"text": t, **index.check(t)} for t in texts]}
