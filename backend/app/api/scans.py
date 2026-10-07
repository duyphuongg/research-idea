from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ScanIn, ScanRunOut, ScanStarted
from app.models import ScanRun
from app.services.scans import execute_scan, resolve_connectors, resolve_jobs, scan_in_progress, try_begin_scan

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
    only = body.sources if body else None
    connectors = resolve_connectors(request.app, session, only)
    jobs = resolve_jobs(request.app, session, only)
    if not connectors and not jobs:
        raise HTTPException(status_code=400, detail="No enabled and configured connectors")
    if not try_begin_scan(request.app):
        raise HTTPException(status_code=409, detail="A scan is already running")
    background.add_task(execute_scan, request.app, connectors, jobs)
    return ScanStarted(sources=[c.name for c in connectors] + [j.name for j in jobs])


@router.get("/scans", response_model=list[ScanRunOut])
def list_scans(
    limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
) -> list[ScanRun]:
    return list(session.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)))
