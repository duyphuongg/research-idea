"""Hourly at minute 15 (launchd): big sports events (World Series, NBA Finals, …) → 🏆 alerts sent right away."""

import asyncio
import logging
from datetime import date, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.connectors.base import ConnectorError
from app.connectors.espn_events import EventsConfig, FinalResult, League, load_events_config, parse_finals
from app.connectors.http import Sleep, request_with_retry
from app.db import utcnow
from app.models import Alert
from app.notify.telegram import send_pending
from app.settings_store import get_setting

logger = logging.getLogger(__name__)
SOURCE = "events"
KIND = "event"


async def fetch_finals(client: httpx.AsyncClient, league: League, us_today: date, sleep: Sleep) -> list[FinalResult]:
    """Today's scoreboard, plus yesterday's while it is postseason (late games roll over the date)."""
    resp = await request_with_retry(client, "GET", league.url, sleep=sleep)
    data = resp.json()
    results = parse_finals(data, league.label, league.stages)
    if (data.get("season") or {}).get("type") == 3:
        yesterday = (us_today - timedelta(days=1)).strftime("%Y%m%d")
        resp = await request_with_retry(client, "GET", league.url, params={"dates": yesterday}, sleep=sleep)
        results += parse_finals(resp.json(), league.label, league.stages)
    return results


def _score(r: FinalResult) -> str:
    if r.winner_score is None or r.loser_score is None:
        return f"{r.winner} thắng {r.loser}"
    return f"{r.winner} {r.winner_score}–{r.loser_score} {r.loser}"


def to_alert(r: FinalResult, now: datetime) -> Alert:
    if r.clinched:
        title = r.champion_text
        reason = f"{r.game_label or r.stage.title}: {_score(r)}"
    else:
        title = f"{r.stage.title} {r.year} · {r.game_label or ''}".rstrip(" ·")
        reason = _score(r)
    if r.series_summary:
        reason += f" · {r.series_summary}"
    return Alert(
        kind=KIND, subject_id=int(r.event_id), level=2 if r.clinched else 1, priority=2.0 if r.clinched else 1.0,
        title=title[:300], reason=f"{r.league} · {reason}"[:300], image_url=r.winner_logo, link="/alerts",
        external_url=None, watch_keyword=None, scan_date=now.date(), created_at=now,
    )


def store_new(session: Session, results: list[FinalResult], now: datetime) -> list[Alert]:
    """One alert per finished game (subject = ESPN event id), never repeated."""
    by_id = {r.event_id: r for r in results if r.event_id.isdigit()}
    if not by_id:
        return []
    done = set(session.scalars(select(Alert.subject_id).where(
        Alert.kind == KIND, Alert.subject_id.in_([int(i) for i in by_id]))))
    alerts = [to_alert(r, now) for i, r in by_id.items() if int(i) not in done]
    alerts.sort(key=lambda a: a.level)
    session.add_all(alerts)
    session.flush()
    return alerts


async def run_events(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    config: EventsConfig | None = None,
    now: datetime | None = None,
    us_today: date | None = None,
    sleep: Sleep = asyncio.sleep,
) -> list[dict] | None:
    """Check the leagues, store new 🏆 alerts and send pending ones (quiet hours apply).

    Returns the new alerts as {title, reason, level, sent}; None when disabled in Settings.
    """
    with session_factory() as session:
        if not (get_setting(session, "connectors_enabled") or {}).get(SOURCE, True):
            return None
    config = config or load_events_config()
    now = now or utcnow()
    us_today = us_today or (now - timedelta(hours=5)).date()
    results: list[FinalResult] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        for league in config.leagues:
            try:
                results += await fetch_finals(client, league, us_today, sleep)
            except (ConnectorError, ValueError, KeyError, TypeError) as exc:
                logger.warning("Events %s failed: %s", league.label, type(exc).__name__)
    with session_factory() as session:
        new = store_new(session, results, now)
        session.commit()
        try:
            await send_pending(session, settings, kinds=(KIND,))
        except Exception:  # Telegram must never break the watcher
            logger.exception("Telegram delivery failed")
        finally:
            session.commit()
        return [{"title": a.title, "reason": a.reason, "level": a.level, "sent": a.sent_at is not None} for a in new]
