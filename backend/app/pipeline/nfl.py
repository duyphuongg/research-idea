"""NFL job: leaders of finished games (ESPN) this week and last, plus shirt demand for the top players."""

import asyncio
import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import ConnectorError
from app.connectors.espn_nfl import SCOREBOARD_URL, ScoreboardWeek, merch_suggestions, parse_scoreboard
from app.connectors.etsy import BASE_URL as ETSY_URL
from app.connectors.google_suggest import SUGGEST_URL
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.models import NflPerformance, NflPlayerDemand
from app.pipeline.scan import MAX_ERROR_LEN, finish_run, start_run

logger = logging.getLogger(__name__)
SOURCE = "nfl"
MAX_PLAYERS = 40  # demand lookups per scan
DEMAND_REFRESH_DAYS = 2


def store_week(session: Session, week: ScoreboardWeek) -> int:
    """Replace the rows of every finished game in this week."""
    events = {p.event_id for p in week.performances}
    if events:
        session.execute(delete(NflPerformance).where(
            NflPerformance.season == week.season, NflPerformance.season_type == week.season_type,
            NflPerformance.week == week.week, NflPerformance.event_id.in_(events),
        ))
    session.add_all(
        NflPerformance(season=week.season, season_type=week.season_type, week=week.week, **vars(p))
        for p in week.performances
    )
    return len(week.performances)


def players_needing_demand(
    session: Session, weeks: list[ScoreboardWeek], today: date, limit: int = MAX_PLAYERS
) -> list[tuple[str, str]]:
    """(athlete_id, name) of the best-scoring players of these weeks without recent demand data."""
    if not weeks:
        return []
    fresh = select(NflPlayerDemand.athlete_id).where(NflPlayerDemand.date > today - timedelta(days=DEMAND_REFRESH_DAYS))
    week_match = [
        (NflPerformance.season == w.season) & (NflPerformance.season_type == w.season_type) & (NflPerformance.week == w.week)
        for w in weeks
    ]
    return [tuple(r) for r in session.execute(
        select(NflPerformance.athlete_id, func.max(NflPerformance.name))
        .where(or_(*week_match), NflPerformance.athlete_id.not_in(fresh))
        .group_by(NflPerformance.athlete_id)
        .order_by(func.max(NflPerformance.points).desc(), NflPerformance.athlete_id)
        .limit(limit)
    )]


async def run_nfl(
    session_factory: sessionmaker[Session],
    etsy_api_key: str | None,
    today: date,
    *,
    min_interval: float = 1.0,
    sleep: Sleep = asyncio.sleep,
) -> int:
    run_id = start_run(session_factory, SOURCE)
    limiter = RateLimiter(min_interval, sleep=sleep)
    errors: list[str] = []
    records = 0
    weeks: list[ScoreboardWeek] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async def scoreboard(params: dict | None = None) -> ScoreboardWeek:
                resp = await request_with_retry(client, "GET", SCOREBOARD_URL, params=params or {},
                                                limiter=limiter, sleep=sleep)
                try:
                    return parse_scoreboard(resp.json())
                except (ValueError, KeyError, TypeError) as exc:
                    raise ConnectorError(f"unexpected ESPN scoreboard: {type(exc).__name__}") from exc

            current = await scoreboard()
            weeks.append(current)
            if current.week > 1:
                try:
                    weeks.append(await scoreboard({"seasontype": current.season_type, "week": current.week - 1}))
                except ConnectorError as exc:
                    errors.append(f"previous week: {exc}")
            with session_factory() as session:
                for week in weeks:
                    records += store_week(session, week)
                session.commit()
                players = players_needing_demand(session, weeks, today)

            for athlete_id, name in players:
                etsy, merch = None, None
                query = f"{name.lower()} shirt"
                if etsy_api_key:
                    try:
                        resp = await request_with_retry(
                            client, "GET", f"{ETSY_URL}/listings/active", limiter=limiter, sleep=sleep,
                            params={"keywords": query, "limit": 1}, headers={"x-api-key": etsy_api_key},
                        )
                        count = resp.json().get("count")
                        etsy = int(count) if isinstance(count, int | float) else None
                    except (ConnectorError, ValueError, AttributeError) as exc:
                        errors.append(f"etsy {query}: {exc}")
                try:
                    resp = await request_with_retry(
                        client, "GET", SUGGEST_URL, limiter=limiter, sleep=sleep,
                        params={"client": "firefox", "hl": "en", "gl": "us", "q": query},
                    )
                    data = resp.json()
                    merch = merch_suggestions([str(s) for s in data[1]])
                except (ConnectorError, ValueError, IndexError, TypeError) as exc:
                    errors.append(f"google {query}: {exc}")
                if etsy is None and merch is None:
                    continue
                with session_factory() as session:
                    row = session.scalar(select(NflPlayerDemand).where(
                        NflPlayerDemand.athlete_id == athlete_id, NflPlayerDemand.date == today))
                    if row is None:
                        row = NflPlayerDemand(athlete_id=athlete_id, date=today)
                        session.add(row)
                    row.etsy_listings, row.merch_suggestions = etsy, merch
                    session.commit()
        status = "partial" if errors else "ok"
    except Exception as exc:  # the scan goes on without NFL data
        logger.warning("NFL job failed: %s", type(exc).__name__)
        errors.append(f"{type(exc).__name__}: {exc}")
        status = "partial" if records else "failed"
    finish_run(session_factory, run_id, SOURCE, status, records,
               "\n".join(errors)[:MAX_ERROR_LEN] if errors else None)
    return run_id
