"""ESPN scoreboards: finished championship-stage games (World Series, NBA Finals, …) and clinches."""

import re
from dataclasses import dataclass
from typing import Any

from app.config_files import load_yaml

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard"
POSTSEASON = 3


@dataclass(frozen=True)
class Stage:
    match: str  # text in ESPN's round headline, e.g. "World Series"
    games: bool  # alert every game (True) or only when the stage is won (False)
    title: str
    champion: str  # "{team} vô địch World Series {year}"


@dataclass(frozen=True)
class League:
    sport: str
    league: str
    label: str
    stages: list[Stage]

    @property
    def url(self) -> str:
        return SCOREBOARD_URL.format(sport=self.sport, league=self.league)


@dataclass(frozen=True)
class EventsConfig:
    leagues: list[League]


def load_events_config() -> EventsConfig:
    data = load_yaml("events.yaml")
    return EventsConfig(leagues=[
        League(
            sport=str(lg["sport"]), league=str(lg["league"]), label=str(lg.get("label") or lg["league"]).upper(),
            stages=[Stage(str(s["match"]), bool(s.get("games", True)), str(s.get("title") or s["match"]),
                          str(s.get("champion") or "{team} vô địch " + str(s["match"])))
                    for s in lg.get("stages") or []],
        )
        for lg in data.get("leagues") or []
    ])


@dataclass(frozen=True)
class FinalResult:
    event_id: str
    league: str
    year: int
    stage: Stage
    headline: str
    game_label: str | None  # "Game 4"; None for a single-game final
    winner: str
    winner_name: str
    winner_logo: str | None
    winner_score: int | None
    loser: str
    loser_score: int | None
    series_summary: str | None
    clinched: bool

    @property
    def champion_text(self) -> str:
        return self.stage.champion.format(team=self.winner_name, year=self.year)


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_finals(data: dict[str, Any], label: str, stages: list[Stage]) -> list[FinalResult]:
    """Finished games of the configured stages in a postseason scoreboard."""
    season = data.get("season") or {}
    if season.get("type") != POSTSEASON:
        return []
    out = []
    for event in data.get("events") or []:
        comp = (event.get("competitions") or [{}])[0]
        status = (comp.get("status") or {}).get("type") or {}
        if not status.get("completed"):
            continue
        headline = next((n.get("headline") for n in comp.get("notes") or [] if n.get("headline")), "") or ""
        stage = next((s for s in stages if s.match.lower() in headline.lower()), None)
        teams = comp.get("competitors") or []
        winner = next((t for t in teams if t.get("winner")), None)
        loser = next((t for t in teams if t is not winner), None)
        if stage is None or winner is None or loser is None:
            continue
        series = comp.get("series")
        clinched = bool(series.get("completed")) if series else True
        if not clinched and not stage.games:
            continue
        game = re.search(r"game\s+(\d+)", headline, re.IGNORECASE)
        out.append(FinalResult(
            event_id=str(event.get("id")), league=label, year=int(season.get("year") or 0), stage=stage,
            headline=headline, game_label=f"Game {game.group(1)}" if game else None,
            winner=winner["team"].get("abbreviation") or "", winner_name=winner["team"].get("displayName") or "",
            winner_logo=winner["team"].get("logo"), winner_score=_int(winner.get("score")),
            loser=loser["team"].get("abbreviation") or "", loser_score=_int(loser.get("score")),
            series_summary=(series or {}).get("summary"), clinched=clinched,
        ))
    return out
