"""Telegram delivery of alerts. The bot token is a secret: it is part of every request URL, so URLs
and raw httpx exceptions must never reach logs or error messages."""

import html
import logging
import re
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.alerts import AlertsConfig, load_alerts_config, telegram_order
from app.config import Settings
from app.db import utcnow
from app.models import Alert

logger = logging.getLogger(__name__)

# httpx logs every request at INFO with the full URL, which contains the bot token.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

API = "https://api.telegram.org"
PENDING_DAYS = 2
TITLE_LIMIT = 90  # raw lengths, cut before escaping so entities and tags stay whole
REASON_LIMIT = 120
CAPTION_LIMIT = 1024  # Telegram's photo/album caption limit, in visible UTF-16 code units
KEYWORD_LIMIT = 40

KIND_STYLE = {
    "niche": ("🚀", "Ngách bứt phá"),
    "listing": ("🔥", "Etsy bứt phá"),
    "shop": ("🏪", "Shop tăng tốc"),
    "hot_product": ("⭐", "Sản phẩm hot"),
    "nfl": ("🏈", "Cầu thủ NFL tiềm năng"),
}


class TelegramError(Exception):
    """Delivery failed. The message never contains the token or the request URL."""


def telegram_configured(settings: Settings) -> bool:
    return bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id)


async def _post(client: httpx.AsyncClient, settings: Settings, method: str, payload: dict) -> int:
    """POST to the Bot API; returns the HTTP status. Raises TelegramError on transport failure."""
    url = f"{API}/bot{settings.telegram_bot_token}/{method}"
    try:
        resp = await client.post(url, json={"chat_id": settings.telegram_chat_id, **payload})
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise TelegramError(f"Telegram request failed: {type(exc).__name__}") from None
    return resp.status_code


def _message(text: str) -> dict:
    return {"text": text, "parse_mode": "HTML", "disable_web_page_preview": True}


async def send_text(settings: Settings, text: str, *, client: httpx.AsyncClient | None = None) -> None:
    if not telegram_configured(settings):
        raise TelegramError("Telegram chưa được cấu hình")
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        status = await _post(client, settings, "sendMessage", _message(text))
    finally:
        if own:
            await client.aclose()
    if status != 200:
        raise TelegramError(f"Telegram trả về HTTP {status}")


def in_quiet_hours(hour: int, cfg: AlertsConfig) -> bool:
    start, end = cfg.quiet_start, cfg.quiet_end
    if start == end:
        return False
    return start <= hour < end if start < end else hour >= start or hour < end


def _item(n: int, alert: Alert, app_url: str | None) -> str:
    icon, label = KIND_STYLE.get(alert.kind, ("🔔", alert.kind))
    head = f"{n}. {icon} <b>{label}</b>"
    if alert.watch_keyword:
        head += f" · {html.escape(alert.watch_keyword[:KEYWORD_LIMIT])}"
    title = html.escape(alert.title[:TITLE_LIMIT])
    if app_url:
        title = f'<a href="{html.escape(app_url + alert.link, quote=True)}">{title}</a>'
    return f"{head}\n{title} — {html.escape(alert.reason[:REASON_LIMIT])}"


def _caption(total: int, items: list[Alert], rest_count: int, app_url: str | None) -> str:
    lines = [f"🔔 <b>{total} tin mới</b>"]
    lines += [_item(n, a, app_url) for n, a in enumerate(items, 1)]
    if rest_count:
        more = f"… và {rest_count} tin khác"
        if app_url:
            more += f' — <a href="{html.escape(app_url + "/alerts", quote=True)}">xem tất cả</a>'
        lines.append(more)
    return "\n".join(lines)


def _visible_len(text: str) -> int:
    """Length Telegram counts: the text after parsing HTML tags and entities."""
    visible = html.unescape(re.sub(r"<[^>]+>", "", text))
    return len(visible.encode("utf-16-le")) // 2  # Telegram counts UTF-16 code units (emoji = 2)


def build_caption(pending: list[Alert], max_items: int, app_url: str | None) -> tuple[str, list[Alert]]:
    """One HTML caption for the whole batch (≤ CAPTION_LIMIT visible UTF-16 units) and the alerts it lists."""
    count = max(1, min(max_items, len(pending)))
    while True:
        items = pending[:count]
        caption = _caption(len(pending), items, len(pending) - count, app_url)
        if count == 1 or _visible_len(caption) <= CAPTION_LIMIT:
            return caption, items
        count -= 1


async def _deliver(client: httpx.AsyncClient, settings: Settings, caption: str, photos: list[str],
                   silent: bool) -> int:
    quiet = {"disable_notification": silent}
    if len(photos) >= 2:
        media = [{"type": "photo", "media": url, **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {})}
                 for i, url in enumerate(photos[:10])]
        status = await _post(client, settings, "sendMediaGroup", {"media": media, **quiet})
    elif photos:
        status = await _post(client, settings, "sendPhoto",
                             {"photo": photos[0], "caption": caption, "parse_mode": "HTML", **quiet})
    else:
        return await _post(client, settings, "sendMessage", {**_message(caption), **quiet})
    # 400 = Telegram could not fetch an image, or rejected the caption (too long / bad HTML): the plain
    # text message below covers all of these, so retry once as text
    if status != 400:
        return status
    return await _post(client, settings, "sendMessage", {**_message(caption), **quiet})


def _high_priority(alert: Alert) -> bool:
    return alert.kind in ("niche", "nfl") or (alert.kind == "listing" and alert.level == 2)


async def send_pending(session: Session, settings: Settings, cfg: AlertsConfig | None = None,
                       *, client: httpx.AsyncClient | None = None, now: datetime | None = None,
                       local_now: datetime | None = None) -> int:
    """Send every pending alert as ONE Telegram notification. Returns how many alerts were marked sent."""
    if not telegram_configured(settings):
        return 0
    cfg = cfg or load_alerts_config()
    local_now = local_now or datetime.now().astimezone()
    if in_quiet_hours(local_now.hour, cfg):
        return 0  # held: the next scan outside quiet hours sends them
    now = now or utcnow()
    pending = list(session.scalars(
        select(Alert).where(Alert.sent_at.is_(None), Alert.created_at >= now - timedelta(days=PENDING_DAYS))
    ))
    if not pending:
        return 0
    pending.sort(key=lambda a: telegram_order(a.kind, a.level, a.priority))
    caption, items = build_caption(pending, cfg.telegram_max_items, settings.app_url)
    photos = [a.image_url for a in items if a.image_url]
    silent = not any(_high_priority(a) for a in pending)

    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        status = await _deliver(client, settings, caption, photos, silent)
    except TelegramError as exc:
        logger.warning("Telegram send failed: %s", exc)
        return 0
    except Exception as exc:  # never log the exception text: it may carry the request URL
        logger.warning("Telegram send failed: %s", type(exc).__name__)
        return 0
    finally:
        if own:
            await client.aclose()
    if status != 200:
        logger.warning("Telegram send failed: %s", status)
        return 0
    for alert in pending:
        alert.sent_at = now
    return len(pending)
