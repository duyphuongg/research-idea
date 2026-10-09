"""Hourly: NFL-related US Google trending searches (Khoảnh khắc NFL) + weekly ESPN roster refresh."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.nfl_match import PlayerIndex, PlayerRef, match_moment
from app.connectors.base import ConnectorError
from app.connectors.etsy import BASE_URL as ETSY_URL
from app.connectors.google_daily import HT_NS, RSS_URL, parse_traffic
from app.connectors.google_suggest import USER_AGENT
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.db import utcnow
from app.models import NflMoment, NflPlayer
from app.pipeline.scan import MAX_ERROR_LEN, finish_run, start_run

logger = logging.getLogger(__name__)
SOURCE = "nfl_moments"
ESPN_TEAMS_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
ROSTER_REFRESH_DAYS = 7
MAX_NEWS = 3


@dataclass(frozen=True)
class Trend:
    query: str
    traffic: int
    published: datetime | None
    picture_url: str | None
    news: list[dict]


def parse_rss(text: str) -> list[Trend]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ConnectorError("invalid trends RSS") from exc
    out = []
    for item in root.iter("item"):
        query = " ".join((item.findtext("title") or "").split())
        if not query:
            continue
        published = None
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            pass
        news = [
            {"title": (n.findtext(f"{HT_NS}news_item_title") or "").strip(),
             "url": n.findtext(f"{HT_NS}news_item_url"), "source": n.findtext(f"{HT_NS}news_item_source")}
            for n in item.findall(f"{HT_NS}news_item")
        ]
        out.append(Trend(
            query=query[:200], traffic=int(parse_traffic(item.findtext(f"{HT_NS}approx_traffic") or "") or 0),
            published=published, picture_url=item.findtext(f"{HT_NS}picture"),
            news=[n for n in news if n["title"]][:MAX_NEWS],
        ))
    return out


async def refresh_rosters(client: httpx.AsyncClient, session: Session, today: date, limiter: RateLimiter,
                          sleep: Sleep) -> int:
    """Reload all 32 rosters when the stored ones are older than ROSTER_REFRESH_DAYS."""
    newest = session.scalar(select(func.max(NflPlayer.updated_on)))
    if newest is not None and newest > today - timedelta(days=ROSTER_REFRESH_DAYS):
        return 0
    resp = await request_with_retry(client, "GET", ESPN_TEAMS_URL, limiter=limiter, sleep=sleep)
    teams = [t["team"] for t in resp.json()["sports"][0]["leagues"][0]["teams"]]
    count = 0
    for team in teams:
        r = await request_with_retry(client, "GET", f"{ESPN_TEAMS_URL}/{team['id']}/roster", limiter=limiter, sleep=sleep)
        for group in r.json().get("athletes") or []:
            for a in group.get("items") or []:
                if not a.get("id") or not a.get("firstName") or not a.get("lastName"):
                    continue
                row = session.get(NflPlayer, str(a["id"])) or NflPlayer(athlete_id=str(a["id"]))
                row.name = a.get("displayName") or f"{a['firstName']} {a['lastName']}"
                row.first_name, row.last_name = a["firstName"][:60], a["lastName"][:60]
                row.team = team.get("abbreviation")
                row.position = (a.get("position") or {}).get("abbreviation")
                row.jersey = a.get("jersey")
                row.headshot_url = (a.get("headshot") or {}).get("href")
                row.updated_on = today
                session.merge(row)
                count += 1
        session.flush()
    session.commit()
    return count


def player_index(session: Session) -> PlayerIndex:
    return PlayerIndex(
        PlayerRef(p.athlete_id, p.first_name, p.last_name, p.team) for p in session.scalars(select(NflPlayer))
    )


def store_trends(
    session: Session, trends: list[Trend], index: PlayerIndex, now: datetime
) -> tuple[list[NflMoment], int]:
    """Upsert the NFL-related trends; returns (moments seen for the first time, NFL trends in this feed)."""
    new, matched = [], 0
    for t in trends:
        match = match_moment(t.query, [n["title"] for n in t.news], index)
        if match is None:
            continue
        matched += 1
        athlete_id, team = match
        moment = session.scalar(select(NflMoment).where(NflMoment.query == t.query.lower()))
        if moment is None:
            moment = NflMoment(query=t.query.lower(), traffic=t.traffic, first_seen=now, last_seen=now,
                               news=t.news, picture_url=t.picture_url, athlete_id=athlete_id, team=team)
            session.add(moment)
            new.append(moment)
        else:
            moment.traffic = max(moment.traffic, t.traffic)
            moment.last_seen = now
            moment.news = t.news or moment.news
            moment.picture_url = t.picture_url or moment.picture_url
            moment.athlete_id, moment.team = athlete_id or moment.athlete_id, team or moment.team
    session.flush()
    return new, matched


async def run_nfl_moments(
    session_factory: sessionmaker[Session],
    etsy_api_key: str | None,
    *,
    now: datetime | None = None,
    min_interval: float = 0.5,
    sleep: Sleep = asyncio.sleep,
) -> int:
    now = now or utcnow()
    run_id = start_run(session_factory, SOURCE)
    limiter = RateLimiter(min_interval, sleep=sleep)
    errors: list[str] = []
    stored = 0
    status = "ok"
    try:
        async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": USER_AGENT}) as client:
            with session_factory() as session:
                try:
                    await refresh_rosters(client, session, now.date(), limiter, sleep)
                except (ConnectorError, ValueError, KeyError, IndexError, TypeError) as exc:
                    session.rollback()
                    errors.append(f"rosters: {type(exc).__name__}: {exc}")
                resp = await request_with_retry(client, "GET", RSS_URL, params={"geo": "US"},
                                                limiter=limiter, sleep=sleep)
                trends = parse_rss(resp.text)
                new, stored = store_trends(session, trends, player_index(session), now)
                session.commit()
                for moment in new:
                    if not etsy_api_key:
                        break
                    try:
                        r = await request_with_retry(
                            client, "GET", f"{ETSY_URL}/listings/active", limiter=limiter, sleep=sleep,
                            params={"keywords": f"{moment.query} shirt", "limit": 1},
                            headers={"x-api-key": etsy_api_key},
                        )
                        count = r.json().get("count")
                        moment.etsy_listings = int(count) if isinstance(count, int | float) else None
                    except (ConnectorError, ValueError, AttributeError) as exc:
                        errors.append(f"etsy {moment.query}: {exc}")
                session.commit()
        if errors:
            status = "partial"
    except Exception as exc:  # never raise out of the hourly job
        logger.warning("NFL moments failed: %s", type(exc).__name__)
        errors.append(f"{type(exc).__name__}: {exc}")
        status = "failed"
    finish_run(session_factory, run_id, SOURCE, status, stored,
               "\n".join(errors)[:MAX_ERROR_LEN] if errors else None)
    return run_id
