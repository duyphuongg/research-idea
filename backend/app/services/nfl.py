"""NFL tuần này: standout players of a week ranked by shirt potential."""

import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.scoring import percentile_ranks
from app.db import utcnow
from app.services.ip import ip_index
from app.models import NflMoment, NflPerformance, NflPlayer, NflPlayerDemand

FULL_WEEK_GAMES = 10  # default to the latest week with at least this many finished games
TRENDING_DAYS = 3
MERCH_FULL, ETSY_FULL_LOG = 10, 4  # 10 apparel suggestions / 10k Etsy listings count as full marks
TRENDING_BONUS = 10


def weeks(session: Session) -> list[dict]:
    rows = session.execute(
        select(NflPerformance.season, NflPerformance.season_type, NflPerformance.week,
               func.count(func.distinct(NflPerformance.event_id)))
        .group_by(NflPerformance.season, NflPerformance.season_type, NflPerformance.week)
        .order_by(NflPerformance.season.desc(), NflPerformance.season_type.desc(), NflPerformance.week.desc())
    )
    return [{"season": s, "season_type": t, "week": w, "games": g} for s, t, w, g in rows]


def potential(performance: float, merch: int | None, etsy: int | None, trending: bool) -> float:
    score = 100 * (
        0.5 * performance
        + 0.3 * min((merch or 0) / MERCH_FULL, 1)
        + 0.2 * min(math.log10((etsy or 0) + 1) / ETSY_FULL_LOG, 1)
    )
    return round(min(100.0, score + (TRENDING_BONUS if trending else 0)), 1)


def _trending_ids(session: Session, athlete_ids: list[str], today: date) -> set[str]:
    """Players with an NFL trending search (Khoảnh khắc NFL) in the last TRENDING_DAYS."""
    since = datetime.combine(today - timedelta(days=TRENDING_DAYS), time())
    return set(session.scalars(select(NflMoment.athlete_id).where(
        NflMoment.athlete_id.in_(athlete_ids), NflMoment.last_seen >= since)))


def standouts(
    session: Session, season: int | None = None, season_type: int | None = None, week: int | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    all_weeks = weeks(session)
    chosen = None
    if week is not None:
        chosen = next((w for w in all_weeks if w["week"] == week
                       and (season is None or w["season"] == season)
                       and (season_type is None or w["season_type"] == season_type)), None)
    elif all_weeks:
        chosen = next((w for w in all_weeks if w["games"] >= FULL_WEEK_GAMES), all_weeks[0])
    if chosen is None:
        return {"season": None, "season_type": None, "week": None, "weeks": all_weeks, "items": []}

    rows = session.scalars(select(NflPerformance).where(
        NflPerformance.season == chosen["season"], NflPerformance.season_type == chosen["season_type"],
        NflPerformance.week == chosen["week"],
    ).order_by(NflPerformance.game_date, NflPerformance.id))
    players: dict[str, dict] = {}
    for r in rows:
        p = players.setdefault(r.athlete_id, {
            "athlete_id": r.athlete_id, "name": r.name, "position": r.position, "jersey": r.jersey,
            "team": r.team, "headshot_url": r.headshot_url, "player_url": r.player_url,
            "games": [], "lines": [], "points": 0.0,
        })
        if r.game not in p["games"]:
            p["games"].append(r.game)
        p["lines"].append({"category": r.category, "stat_line": r.stat_line})
        p["points"] = round(p["points"] + r.points, 2)
    picked = {k: chosen[k] for k in ("season", "season_type", "week")}
    if not players:
        return {**picked, "weeks": all_weeks, "items": []}

    latest_demand = (select(NflPlayerDemand.athlete_id, func.max(NflPlayerDemand.date).label("d"))
                     .where(NflPlayerDemand.athlete_id.in_(players)).group_by(NflPlayerDemand.athlete_id).subquery())
    demand = {d.athlete_id: d for d in session.scalars(select(NflPlayerDemand).join(
        latest_demand, (NflPlayerDemand.athlete_id == latest_demand.c.athlete_id)
        & (NflPlayerDemand.date == latest_demand.c.d)))}
    perf = percentile_ranks({aid: p["points"] for aid, p in players.items()})
    trending = _trending_ids(session, list(players), today)

    items = []
    for aid, p in players.items():
        d = demand.get(aid)
        etsy, merch = (d.etsy_listings, d.merch_suggestions) if d else (None, None)
        hot = aid in trending
        items.append({
            **p, "performance": round(perf[aid], 3), "etsy_listings": etsy, "merch_suggestions": merch,
            "trending": hot, "potential": potential(perf[aid], merch, etsy, hot),
        })
    items.sort(key=lambda i: (-i["potential"], -i["points"], i["name"]))
    return {**picked, "weeks": all_weeks, "items": items}


def moments(session: Session, days: int = 7, now: datetime | None = None) -> list[dict]:
    """NFL trending searches seen in the last `days`, biggest first."""
    now = now or utcnow()
    rows = session.scalars(select(NflMoment).where(NflMoment.last_seen >= now - timedelta(days=days)))
    index = ip_index(session)
    out = []
    for m in rows:
        player = session.get(NflPlayer, m.athlete_id) if m.athlete_id else None
        out.append({
            "id": m.id, "query": m.query, "traffic": m.traffic, "first_seen": m.first_seen, "last_seen": m.last_seen,
            "news": m.news or [], "picture_url": m.picture_url, "etsy_listings": m.etsy_listings, "team": m.team,
            "ip_level": index.check(m.query)["level"],
            "player": None if player is None else {
                "athlete_id": player.athlete_id, "name": player.name, "team": player.team,
                "position": player.position, "headshot_url": player.headshot_url,
            },
        })
    out.sort(key=lambda m: (-m["traffic"], -m["last_seen"].timestamp()))
    return out
