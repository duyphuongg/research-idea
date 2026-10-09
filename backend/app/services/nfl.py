"""NFL tuần này: standout players of a week ranked by shirt potential."""

import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.scoring import percentile_ranks
from app.models import Keyword, NflPerformance, NflPlayerDemand, TrendSignal

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


def _trending_names(session: Session, names: set[str], today: date) -> set[str]:
    texts = list(session.scalars(
        select(Keyword.text).join(TrendSignal, TrendSignal.keyword_id == Keyword.id)
        .where(TrendSignal.source == "google_daily", TrendSignal.date > today - timedelta(days=TRENDING_DAYS))
        .distinct()
    ))
    return {n for n in names if any(n.lower() in t for t in texts)}


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
    trending = _trending_names(session, {p["name"] for p in players.values()}, today)

    items = []
    for aid, p in players.items():
        d = demand.get(aid)
        etsy, merch = (d.etsy_listings, d.merch_suggestions) if d else (None, None)
        hot = p["name"] in trending
        items.append({
            **p, "performance": round(perf[aid], 3), "etsy_listings": etsy, "merch_suggestions": merch,
            "trending": hot, "potential": potential(perf[aid], merch, etsy, hot),
        })
    items.sort(key=lambda i: (-i["potential"], -i["points"], i["name"]))
    return {**picked, "weeks": all_weeks, "items": items}
