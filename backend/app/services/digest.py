"""Weekly Telegram digest: top rising niches, watchlist, top shops, upcoming US events and last week's alerts."""

import html
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.alerts import AlertsConfig, load_alerts_config
from app.analysis.listing_signals import load_signals_config
from app.analysis.us_calendar import PHASE_LABEL, load_calendar, occurrences, phase
from app.config import Settings
from app.db import utcnow
from app.models import Alert, Keyword, KeywordScore, ListingSignal, Product
from app.notify.telegram import KIND_STYLE, TelegramError, in_quiet_hours, send_text, telegram_configured
from app.services.shops import is_full_window, shop_metrics, shops_matching
from app.services.watchlist import listing_keyword_filter, seed_keyword_ids, watch_keywords
from app.settings_store import get_setting, set_setting

logger = logging.getLogger(__name__)

TEXT_LIMIT = 4096  # Telegram sendMessage limit
TOP_N = 5
TOP_SHOPS = 3
MAX_EVENTS = 4
EVENT_HORIZON_DAYS = 60
BREAKOUT = ("super_breakout", "steady_grower")


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _link(text: str, url: str | None) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{_esc(text)}</a>' if url else _esc(text)


def _rising(session: Session, app_url: str | None) -> list[str]:
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return []
    now_rows = session.execute(
        select(Keyword.id, Keyword.text, KeywordScore.score)
        .join(Keyword, Keyword.id == KeywordScore.keyword_id)
        .where(KeywordScore.date == latest, Keyword.is_pod_relevant.is_(True))
    ).all()
    if not now_rows:
        return []
    ids = [r.id for r in now_rows]
    lo, hi = latest - timedelta(days=14), latest - timedelta(days=7)
    base_date = (
        select(KeywordScore.keyword_id, func.max(KeywordScore.date).label("d"))
        .where(KeywordScore.keyword_id.in_(ids), KeywordScore.date >= lo, KeywordScore.date <= hi)
        .group_by(KeywordScore.keyword_id).subquery()
    )
    base = dict(session.execute(
        select(KeywordScore.keyword_id, KeywordScore.score).join(
            base_date, (KeywordScore.keyword_id == base_date.c.keyword_id) & (KeywordScore.date == base_date.c.d))
    ).all())

    def name(r) -> str:
        return _link(r.text, f"{app_url}/trends/{r.id}" if app_url else None)

    if not base:
        top = sorted(now_rows, key=lambda r: (-r.score, r.text))[:TOP_N]
        return ["🚀 <b>Ngách điểm cao nhất</b>"] + [
            f"{n}. {name(r)} — {round(r.score)}" for n, r in enumerate(top, 1)]
    deltas = [(r, round(r.score) - round(base[r.id])) for r in now_rows if r.id in base]
    top = sorted((t for t in deltas if t[1] > 0), key=lambda t: (-t[1], -t[0].score, t[0].text))[:TOP_N]
    if not top:
        return []
    return ["🚀 <b>Ngách tăng mạnh nhất 7 ngày</b>"] + [
        f"{n}. {name(r)} — {round(r.score)} (+{d})" for n, (r, d) in enumerate(top, 1)]


def _watchlist(session: Session, since: datetime) -> list[str]:
    seeds = watch_keywords(session)
    if not seeds:
        return []
    suffix = load_signals_config().seed_query_suffix
    latest_listing = session.scalar(select(func.max(ListingSignal.updated_on)))
    alert_counts = dict(session.execute(
        select(Alert.watch_keyword, func.count())
        .where(Alert.created_at >= since, Alert.watch_keyword.is_not(None))
        .group_by(Alert.watch_keyword)).all())
    lines = ["👀 <b>Watchlist</b>"]
    for seed in seeds:
        ids = seed_keyword_ids(session, seed.keyword)
        score = None
        if ids:
            score = session.scalar(select(KeywordScore.score).where(KeywordScore.keyword_id == ids[0])
                                   .order_by(KeywordScore.date.desc()).limit(1))
        breakouts = 0
        if latest_listing:
            breakouts = session.scalar(
                select(func.count()).select_from(ListingSignal)
                .join(Product, Product.id == ListingSignal.product_id)
                .where(ListingSignal.updated_on == latest_listing, ListingSignal.status.in_(BREAKOUT),
                       listing_keyword_filter(seed.keyword, suffix))) or 0
        shown = "—" if score is None else str(round(score))
        lines.append(f"• {_esc(seed.keyword)}: {shown} điểm · {breakouts} bứt phá · "
                     f"{alert_counts.get(seed.keyword, 0)} tin")
    return lines


def _top_shops(session: Session, app_url: str | None) -> list[str]:
    """Shops selling the most over a full 7 days, among shops matching any watch keyword."""
    ids: set[int] = set()
    for seed in watch_keywords(session):
        ids |= shops_matching(session, seed.keyword)
    if not ids:
        return []
    rows = [m for m in shop_metrics(session, ids) if is_full_window(m.sales_7d, 7) and m.sales_7d.value >= 1]
    if not rows:
        return []
    rows.sort(key=lambda m: (-m.sales_7d.value, m.shop.name, m.shop.id))
    return ["🏪 <b>Shop ra đơn nhiều nhất 7 ngày</b>"] + [
        f"• {_link(m.shop.name, f'{app_url}/shops/{m.shop.id}' if app_url else None)} — +{m.sales_7d.value} đơn"
        for m in rows[:TOP_SHOPS]
    ]


def _upcoming(today: date) -> list[str]:
    cfg = load_calendar()
    occs = [o for o in occurrences(cfg.events, today, EVENT_HORIZON_DAYS) if o.start >= today]
    occs.sort(key=lambda o: (o.start, o.event.key))
    if not occs:
        return []
    lines = ["📅 <b>Sắp tới</b>"]
    for occ in occs[:MAX_EVENTS]:
        days = (occ.start - today).days
        when = "hôm nay" if days == 0 else f"còn {days} ngày"
        label = PHASE_LABEL[phase(occ, today, cfg.fulfillment_days, cfg.ship_buffer_days)]
        lines.append(f"• {_esc(occ.event.name)} {occ.start:%d/%m} — {when} · {label}")
    return lines


def _alert_summary(session: Session, since: datetime, app_url: str | None) -> list[str]:
    counts = dict(session.execute(
        select(Alert.kind, func.count()).where(Alert.created_at >= since).group_by(Alert.kind)).all())
    total = sum(counts.values())
    if total:
        order = list(KIND_STYLE) + sorted(k for k in counts if k not in KIND_STYLE)
        parts = [f"{counts[k]} {KIND_STYLE.get(k, ('🔔', k))[0]}" for k in order if counts.get(k)]
        line = f"🔔 <b>Tuần qua:</b> {total} tin ({' · '.join(parts)})"
    else:
        line = "🔔 <b>Tuần qua:</b> chưa có tin"
    lines = [line]
    if app_url:
        lines.append(f'<a href="{html.escape(app_url + "/alerts", quote=True)}">Mở app →</a>')
    return lines


def _join(sections: list[list[str]]) -> str:
    return "\n\n".join("\n".join(s) for s in sections if s)


def build_digest(session: Session, today: date, app_url: str | None, *, now: datetime | None = None) -> str:
    """HTML digest (≤ TEXT_LIMIT chars) for the 7 days before `today`. `now` is naive UTC."""
    since = (now or utcnow()) - timedelta(days=7)
    start, end = today - timedelta(days=7), today - timedelta(days=1)
    header = [f"📊 <b>Tổng kết 7 ngày qua ({start:%d/%m} – {end:%d/%m})</b>"]
    body = [_rising(session, app_url), _watchlist(session, since), _top_shops(session, app_url), _upcoming(today)]
    footer = _alert_summary(session, since, app_url)
    while len(text := _join([header, *body, footer])) > TEXT_LIMIT:
        longest = max((s for s in body if len(s) > 1), key=lambda s: len("\n".join(s)), default=None)
        if longest is None:
            return text[:TEXT_LIMIT]  # unreachable in practice: header + footer alone are short
        longest.pop()
        if len(longest) == 1:
            longest.clear()  # a heading with no rows is dropped
    return text


def iso_week(d: date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


async def maybe_send_weekly_digest(session: Session, settings: Settings, *, local_now: datetime | None = None,
                                   cfg: AlertsConfig | None = None,
                                   client: httpx.AsyncClient | None = None) -> bool:
    """Send the digest once per ISO week (the first scan of the week outside quiet hours). True if sent."""
    if not telegram_configured(settings):
        return False
    cfg = cfg or load_alerts_config()
    local_now = local_now or datetime.now().astimezone()
    if in_quiet_hours(local_now.hour, cfg):
        return False
    week = iso_week(local_now.date())
    last = get_setting(session, "digest_last_week")
    if last is None:  # first run after deploy: no mid-week digest, the first one goes out next week
        set_setting(session, "digest_last_week", week)
        return False
    if last == week:
        return False
    text = build_digest(session, local_now.date(), settings.app_url)
    try:
        await send_text(settings, text, client=client)
    except TelegramError as exc:
        logger.warning("Weekly digest failed: %s", exc)
        return False
    set_setting(session, "digest_last_week", week)
    return True
