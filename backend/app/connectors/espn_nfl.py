"""ESPN public NFL scoreboard: leaders of finished games, scored fantasy-style."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
FINAL = "STATUS_FINAL"
CATEGORIES = ("passingYards", "rushingYards", "receivingYards")
# points per unit by category (fantasy-style)
POINTS = {
    "passingYards": {"YDS": 1 / 25, "TD": 4, "INT": -2},
    "rushingYards": {"YDS": 1 / 10, "TD": 6},
    "receivingYards": {"YDS": 1 / 10, "TD": 6, "REC": 0.5},
}
_STAT = re.compile(r"(-?\d+)\s+(YDS|TD|INT|REC|CAR)\b")
_MERCH = re.compile(r"\b(shirts?|tees?|t-shirts?|tshirts?|hoodies?|sweatshirts?|jerseys?)\b")


@dataclass(frozen=True)
class Performance:
    event_id: str
    game: str
    game_date: datetime | None
    athlete_id: str
    name: str
    position: str | None
    jersey: str | None
    team: str | None
    category: str
    stat_line: str
    points: float
    headshot_url: str | None
    player_url: str | None


@dataclass
class ScoreboardWeek:
    season: int
    season_type: int
    week: int
    performances: list[Performance] = field(default_factory=list)


def stat_points(category: str, line: str) -> float:
    weights = POINTS.get(category, {})
    return sum(int(n) * weights.get(unit, 0) for n, unit in _STAT.findall(line))


def merch_suggestions(suggestions: list[str]) -> int:
    """Google suggestions that are about apparel ("shirtless" does not count)."""
    return sum(1 for s in suggestions if _MERCH.search(s.lower()))


def _date(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_scoreboard(data: dict[str, Any]) -> ScoreboardWeek:
    week = ScoreboardWeek(
        season=int(data["season"]["year"]), season_type=int(data["season"]["type"]),
        week=int(data["week"]["number"]),
    )
    for event in data.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        if comp.get("status", {}).get("type", {}).get("name") != FINAL:
            continue  # unfinished games list season-to-date leaders
        teams = {str(c["team"]["id"]): c["team"].get("abbreviation") for c in comp.get("competitors") or []
                 if "team" in c}
        for group in comp.get("leaders") or []:
            category = group.get("name")
            if category not in CATEGORIES:
                continue
            for leader in (group.get("leaders") or [])[:1]:
                athlete = leader.get("athlete") or {}
                line = leader.get("displayValue")
                if not athlete.get("id") or not athlete.get("displayName") or not line:
                    continue
                links = athlete.get("links") or [{}]
                week.performances.append(Performance(
                    event_id=str(event.get("id")), game=str(event.get("name") or ""),
                    game_date=_date(event.get("date")), athlete_id=str(athlete["id"]),
                    name=athlete["displayName"], position=(athlete.get("position") or {}).get("abbreviation"),
                    jersey=athlete.get("jersey"), team=teams.get(str((athlete.get("team") or {}).get("id"))),
                    category=category, stat_line=line, points=round(stat_points(category, line), 2),
                    headshot_url=athlete.get("headshot"), player_url=links[0].get("href"),
                ))
    return week
