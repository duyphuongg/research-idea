import json
from pathlib import Path

import pytest

from app.connectors.espn_nfl import merch_suggestions, parse_scoreboard, stat_points

FIXTURE = json.loads((Path(__file__).parent / "fixtures/espn/scoreboard.json").read_text())


def test_stat_points():
    assert stat_points("passingYards", "24/42, 316 YDS, 1 TD, 2 INT") == pytest.approx(316 / 25 + 4 - 4)
    assert stat_points("rushingYards", "21 CAR, 165 YDS, 1 TD") == pytest.approx(16.5 + 6)
    assert stat_points("receivingYards", "9 REC, 130 YDS, 1 TD") == pytest.approx(13 + 6 + 4.5)
    assert stat_points("receivingYards", "-3 YDS") == pytest.approx(-0.3)
    assert stat_points("tackles", "12 TOT") == 0


def test_parse_scoreboard_keeps_only_final_games():
    week = parse_scoreboard(FIXTURE)
    assert (week.season, week.season_type, week.week) == (2026, 2, 5)
    assert len(week.performances) == 3
    dak = next(p for p in week.performances if p.category == "passingYards")
    assert (dak.name, dak.athlete_id, dak.team, dak.position, dak.jersey) == ("Dak Prescott", "2577417", "DAL", "QB", "4")
    assert dak.game == "Tampa Bay Buccaneers at Dallas Cowboys" and dak.event_id
    assert dak.player_url.startswith("https://www.espn.com/nfl/player/")
    assert dak.headshot_url.endswith("2577417.png") and dak.game_date is not None
    assert {p.name for p in week.performances} == {"Dak Prescott", "Bucky Irving", "George Pickens"}


def test_parse_scoreboard_tolerates_missing_parts():
    week = parse_scoreboard({"season": {"year": 2026, "type": 2}, "week": {"number": 1}, "events": [
        {"id": "1", "name": "A at B", "competitions": [{"status": {"type": {"name": "STATUS_FINAL"}},
                                                       "leaders": [{"name": "passingYards", "leaders": [{}]}]}]},
    ]})
    assert week.performances == []


def test_merch_suggestions():
    s = ["bucky irving shirt", "bucky irving shirtless", "bucky irving jersey youth", "bucky irving age",
         "bucky irving t-shirt", "bucky irving hoodie"]
    assert merch_suggestions(s) == 4
