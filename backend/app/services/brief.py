"""Morning brief ("Hôm nay làm gì"): one Telegram message a day with the few things worth doing today."""

import html
import logging
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.alerts import AlertsConfig, load_alerts_config
from app.analysis.us_calendar import PHASE_LABEL, load_calendar, milestones, occurrences, phase
from app.config import Settings
from app.db import utcnow
from app.models import Alert, Keyword, KeywordScore, NflMoment, WorkItem
from app.notify.telegram import TelegramError, in_quiet_hours, send_text, telegram_configured
from app.services.ip import ip_index
from app.services.niche import opportunity  # the same "Cơ hội" as the Trend Radar sort
from app.services.nfl import standouts
from app.services.work import DONE, describe
from app.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)
SETTING = "brief_last_date"
BRIEF_HOURS = range(7, 12)  # the morning scan sends it
ACTIVE_PHASES = ("design", "launch", "push")
ORDER_SOON_DAYS = 10
MAX_EVENTS, MAX_OPPORTUNITIES = 2, 3
STALE_DESIGN_DAYS, STALE_IDEA_DAYS = 5, 7
NFL_MIN_POTENTIAL = 85
NFL_FRESH_DAYS = 8


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _link(app_url: str | None, path: str, text: str) -> str:
    if not app_url:
        return _esc(text)
    return f'<a href="{html.escape(app_url + path, quote=True)}">{_esc(text)}</a>'


def _calendar(today: date) -> list[str]:
    cfg = load_calendar()
    lines = []
    for occ in occurrences(cfg.events, today, 120):
        if occ.start <= today:  # already running: nothing left to prepare
            continue
        current = phase(occ, today, cfg.fulfillment_days, cfg.ship_buffer_days)
        m = milestones(occ, cfg.fulfillment_days, cfg.ship_buffer_days)
        order_in = (m.order_by - today).days
        if current not in ACTIVE_PHASES and not 0 <= order_in <= ORDER_SOON_DAYS:
            continue
        line = f"• {_esc(occ.event.name)} còn {(occ.start - today).days} ngày — {PHASE_LABEL[current]}"
        if 0 <= order_in <= ORDER_SOON_DAYS:
            line += f", hạn đặt hàng {m.order_by:%d/%m}"
        lines.append(line)
        if len(lines) >= MAX_EVENTS:
            break
    return ["📅 <b>Mùa vụ</b>", *lines] if lines else []


def _opportunities(session: Session, app_url: str | None) -> list[str]:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return []
    done = set(session.scalars(select(WorkItem.subject_id).where(
        WorkItem.subject_kind == "keyword", WorkItem.status.in_(DONE))))
    rows = session.execute(
        select(KeywordScore, Keyword).join(Keyword, Keyword.id == KeywordScore.keyword_id)
        .where(KeywordScore.date == latest, Keyword.is_pod_relevant.is_(True))
    ).all()
    index = ip_index(session)
    ranked = sorted(
        ((opportunity(s), k) for s, k in rows if opportunity(s) is not None and k.id not in done),
        key=lambda x: (-x[0], x[1].id),
    )
    lines = []
    for value, kw in ranked:
        if index.check(kw.text)["level"] == "red":
            continue
        path = "/niche?" + urlencode({"keyword": kw.text})
        lines.append(f"• {_link(app_url, path, kw.text)} — cơ hội {value:.0f}")
        if len(lines) >= MAX_OPPORTUNITIES:
            break
    return ["🎯 <b>Ngách nên làm</b>", *lines] if lines else []


def _nfl(session: Session, now: datetime, app_url: str | None) -> list[str]:
    lines = []
    page = standouts(session, today=now.date())
    top = page["items"][0] if page["items"] else None
    if top and top["potential"] >= NFL_MIN_POTENTIAL:
        lines.append(f"• Tuần {page['week']}: {_esc(top['name'])} ({_esc(top['team'] or '')}) — "
                     f"{_esc('; '.join(line['stat_line'] for line in top['lines']))}, tiềm năng {top['potential']:.0f}")
    moment = session.scalar(select(NflMoment).where(NflMoment.last_seen >= now - timedelta(hours=24))
                            .order_by(NflMoment.traffic.desc()).limit(1))
    if moment is not None:
        lines.append(f"• Đang hot: {_esc(moment.query)} ({moment.traffic:,}+ lượt tìm)".replace(",", "."))
    return ["🏈 <b>NFL</b>", *lines] if lines else []


def _work(session: Session, now: datetime, app_url: str | None) -> list[str]:
    lines = []
    for status, days, label in (("designing", STALE_DESIGN_DAYS, "đang thiết kế"), ("idea", STALE_IDEA_DAYS, "ý tưởng")):
        items = list(session.scalars(select(WorkItem).where(
            WorkItem.status == status, WorkItem.updated_at <= now - timedelta(days=days)
        ).order_by(WorkItem.updated_at)))
        if items:
            names = ", ".join(_esc(describe(session, i)["title"][:40]) for i in items[:2])
            more = f" và {len(items) - 2} mục khác" if len(items) > 2 else ""
            lines.append(f"• {len(items)} mục {label} ≥ {days} ngày chưa cập nhật: {names}{more}")
    return [f"🗂 <b>{_link(app_url, '/work', 'Việc của tôi')}</b>", *lines] if lines else []


def build_brief(session: Session, today: date, app_url: str | None, *, now: datetime | None = None) -> str | None:
    """HTML brief, or None when there is nothing worth saying."""
    now = now or utcnow()
    sections = [_calendar(today), _opportunities(session, app_url), _nfl(session, now, app_url),
                _work(session, now, app_url)]
    if not any(sections):
        return None
    unread = session.scalar(select(func.count()).select_from(Alert).where(Alert.read_at.is_(None))) or 0
    footer = [f"🔔 {_link(app_url, '/alerts', f'{unread} tin chưa đọc')}"] if unread else []
    head = [f"☀️ <b>Hôm nay làm gì — {today:%d/%m}</b>"]
    return "\n\n".join("\n".join(s) for s in [head, *sections, footer] if s)


async def maybe_send_morning_brief(session: Session, settings: Settings, *, local_now: datetime | None = None,
                                   cfg: AlertsConfig | None = None,
                                   client: httpx.AsyncClient | None = None) -> bool:
    """Send once per local day, from the first scan between 07:00 and 11:59 outside quiet hours. True if sent."""
    if not telegram_configured(settings):
        return False
    cfg = cfg or load_alerts_config()
    local_now = local_now or datetime.now().astimezone()
    if local_now.hour not in BRIEF_HOURS or in_quiet_hours(local_now.hour, cfg):
        return False
    today = local_now.date()
    if get_setting(session, SETTING) == today.isoformat():
        return False
    text = build_brief(session, today, settings.app_url)
    if text is None:
        set_setting(session, SETTING, today.isoformat())
        return False
    try:
        await send_text(settings, text, client=client)
    except TelegramError as exc:
        logger.warning("Morning brief failed: %s", exc)
        return False
    set_setting(session, SETTING, today.isoformat())
    return True
