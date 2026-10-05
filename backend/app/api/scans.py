from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ScanIn, ScanRunOut, ScanStarted
from app.models import ScanRun
from app.services.scans import execute_scan, resolve_connectors, scan_in_progress

router = APIRouter(prefix="/api")


@router.post("/scans", response_model=ScanStarted, status_code=202)
def start_scan(
    background: BackgroundTasks,
    request: Request,
    body: ScanIn | None = None,
    session: Session = Depends(get_session),
) -> ScanStarted:
    if scan_in_progress(session):
        raise HTTPException(status_code=409, detail="A scan is already running")
    connectors = resolve_connectors(request.app, session, body.sources if body else None)
    if not connectors:
        raise HTTPException(status_code=400, detail="No enabled and configured connectors")
    background.add_task(execute_scan, request.app, connectors)
    return ScanStarted(sources=[c.name for c in connectors])


@router.get("/scans", response_model=list[ScanRunOut])
def list_scans(
    limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
) -> list[ScanRun]:
    return list(session.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)))
