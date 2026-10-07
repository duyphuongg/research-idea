from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import AlertOut, AlertPage, TelegramStatus, UnreadCount
from app.db import utcnow
from app.models import Alert
from app.notify.telegram import TelegramError, send_text, telegram_configured

router = APIRouter(prefix="/api")


def _unread(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Alert).where(Alert.read_at.is_(None))) or 0


def _alert_out(a: Alert) -> AlertOut:
    return AlertOut(
        id=a.id, kind=a.kind, level=a.level, title=a.title, reason=a.reason, image_url=a.image_url,
        link=a.link, external_url=a.external_url, watch_keyword=a.watch_keyword, scan_date=a.scan_date,
        created_at=a.created_at, read=a.read_at is not None,
    )


@router.get("/alerts", response_model=AlertPage)
def list_alerts(limit: int = Query(100, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.scalars(select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit))
    items = [_alert_out(a) for a in rows]
    return AlertPage(unread=_unread(session), items=items)


@router.get("/alerts/unread-count", response_model=UnreadCount)
def unread_count(session: Session = Depends(get_session)):
    return UnreadCount(unread=_unread(session))


@router.post("/alerts/read", response_model=UnreadCount)
def mark_read(session: Session = Depends(get_session)):
    session.execute(update(Alert).where(Alert.read_at.is_(None)).values(read_at=utcnow()))
    session.commit()
    return UnreadCount(unread=0)


@router.get("/alerts/telegram", response_model=TelegramStatus)
def telegram_status(request: Request):
    settings = request.app.state.settings
    return TelegramStatus(configured=telegram_configured(settings), app_url=settings.app_url)


@router.post("/alerts/test")
async def test_message(request: Request):
    settings = request.app.state.settings
    if not telegram_configured(settings):
        raise HTTPException(400, "Chưa cấu hình Telegram — chạy make telegram-setup")
    try:
        await send_text(settings, "🔔 Tin thử từ POD Trend Radar")
    except TelegramError as exc:
        raise HTTPException(502, f"Telegram từ chối: {exc}") from None
    return {"ok": True}
