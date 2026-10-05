from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import SourceHealthOut
from app.connectors.registry import connector_status
from app.models import ScanRun
from app.settings_store import get_setting

router = APIRouter(prefix="/api")


@router.get("/health/sources", response_model=list[SourceHealthOut])
def sources_health(request: Request, session: Session = Depends(get_session)) -> list[SourceHealthOut]:
    overrides = get_setting(session, "connectors_enabled")
    out = []
    for status in connector_status(request.app.state.settings, overrides):
        last = session.scalar(
            select(ScanRun)
            .where(ScanRun.source == status["name"], ScanRun.status != "running")
            .order_by(ScanRun.id.desc())
            .limit(1)
        )
        out.append(
            SourceHealthOut(
                **status,
                last_status=last.status if last else None,
                last_finished_at=last.finished_at if last else None,
                last_error=last.error if last else None,
            )
        )
    return out
