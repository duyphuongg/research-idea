"""Telegram delivery of alerts. The bot token is a secret: it is part of every request URL, so URLs
and raw httpx exceptions must never reach logs or error messages."""

import html
import logging
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
TITLE_LIMIT = 200  # raw lengths, cut before escaping so entities and tags stay whole
REASON_LIMIT = 300

KIND_STYLE = {
    "niche": ("🚀", "Ngách bứt phá"),
    "listing": ("🔥", "Etsy bứt phá"),
    "hot_product": ("⭐", "Sản phẩm hot"),
    "amazon": ("🛒", "Amazon mới vào top"),
}


class TelegramError(Exception):
    """Delivery failed. The message never contains the token or the request URL."""


def telegram_configured(settings: Settings) -> bool:
    return bool(settings.telegram_bot_token) and bool(settings.telegram_chat_id)


def format_caption(alert: Alert, app_url: str | None) -> str:
    icon, title = KIND_STYLE.get(alert.kind, ("🔔", alert.kind))
    head = f"{icon} <b>{title}</b>"
    if alert.watch_keyword:
        head += f" · {html.escape(alert.watch_keyword)}"
    links = []
    if app_url:
        links.append(f'<a href="{html.escape(app_url + alert.link, quote=True)}">Mở trong app</a>')
    if alert.external_url:
        label = "Amazon" if "amazon." in alert.external_url else "Etsy"
        links.append(f'<a href="{html.escape(alert.external_url, quote=True)}">{label}</a>')
    lines = [head, html.escape(alert.title[:TITLE_LIMIT]), html.escape(alert.reason[:REASON_LIMIT])]
    if links:
        lines.append(" · ".join(links))
    return "\n".join(lines)


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


async def _send_alert(client: httpx.AsyncClient, settings: Settings, alert: Alert) -> int:
    caption = format_caption(alert, settings.app_url)
    if alert.image_url:
        status = await _post(client, settings, "sendPhoto",
                             {"photo": alert.image_url, "caption": caption, "parse_mode": "HTML"})
        if status != 400:
            return status
    return await _post(client, settings, "sendMessage", _message(caption))


async def send_pending(session: Session, settings: Settings, cfg: AlertsConfig | None = None,
                       *, client: httpx.AsyncClient | None = None, now: datetime | None = None) -> int:
    if not telegram_configured(settings):
        return 0
    cfg = cfg or load_alerts_config()
    now = now or utcnow()
    pending = list(session.scalars(
        select(Alert).where(Alert.sent_at.is_(None), Alert.created_at >= now - timedelta(days=PENDING_DAYS))
    ))
    if not pending:
        return 0
    pending.sort(key=lambda a: telegram_order(a.kind, a.level, a.priority))
    top, rest = pending[: cfg.telegram_max_items], pending[cfg.telegram_max_items:]

    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    sent = 0
    try:
        for alert in top:
            try:
                status = await _send_alert(client, settings, alert)
            except TelegramError as exc:  # transport failure: Telegram unreachable, leave the rest pending
                logger.warning("Telegram send failed: %s", exc)
                return sent
            except Exception as exc:  # never let one alert lose the sent_at of the others
                logger.warning("Telegram send failed: %s", type(exc).__name__)
                continue
            if status == 200:
                alert.sent_at = now
                sent += 1
            elif status == 429:
                return sent
            else:
                logger.warning("Telegram send failed: %s", status)
        if rest:
            text = f"… và {len(rest)} tin khác"
            text += f" — xem trong app: {html.escape(settings.app_url + '/alerts')}" if settings.app_url else ""
            try:
                status = await _post(client, settings, "sendMessage", _message(text))
            except TelegramError as exc:
                logger.warning("Telegram send failed: %s", exc)
                return sent
            if status == 200:
                for alert in rest:
                    alert.sent_at = now
                sent += len(rest)
            else:
                logger.warning("Telegram send failed: %s", status)
        return sent
    finally:
        if own:
            await client.aclose()
