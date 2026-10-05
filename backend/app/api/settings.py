from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ConnectorStatusOut, SettingsIn, SettingsOut
from app.connectors.registry import connector_status
from app.settings_store import get_setting, set_setting

router = APIRouter(prefix="/api")


def settings_out(request: Request, session: Session) -> SettingsOut:
    overrides = get_setting(session, "connectors_enabled")
    return SettingsOut(
        scan_hour_utc=get_setting(session, "scan_hour_utc"),
        connectors=[
            ConnectorStatusOut(**c) for c in connector_status(request.app.state.settings, overrides)
        ],
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(request: Request, session: Session = Depends(get_session)) -> SettingsOut:
    return settings_out(request, session)


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: SettingsIn, request: Request, session: Session = Depends(get_session)
) -> SettingsOut:
    if body.connectors_enabled is not None:
        known = {c["name"] for c in connector_status(request.app.state.settings, {})}
        unknown = sorted(set(body.connectors_enabled) - known)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown connectors: {unknown}")
        merged = {**get_setting(session, "connectors_enabled"), **body.connectors_enabled}
        set_setting(session, "connectors_enabled", merged)
    if body.scan_hour_utc is not None:
        set_setting(session, "scan_hour_utc", body.scan_hour_utc)
    session.commit()
    return settings_out(request, session)
