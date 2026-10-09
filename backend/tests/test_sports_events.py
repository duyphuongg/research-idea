import json
from pathlib import Path

from app.connectors.espn_events import EventsConfig, Stage, load_events_config, parse_finals

FIXTURE = json.loads((Path(__file__).parent / "fixtures/espn/mlb_postseason.json").read_text())
STAGES = [
    Stage("World Series", True, "World Series", "{team} vô địch World Series {year}"),
    Stage("ALCS", False, "ALCS", "{team} vô địch American League {year}"),
]


def test_parse_finals_game_and_clinch():
    results = {r.event_id: r for r in parse_finals(FIXTURE, "MLB", STAGES)}
    assert set(results) == {"401999004", next(e["id"] for e in FIXTURE["events"] if e["id"] not in
                                              ("401999004", "401999001", "401999005"))}
    g4 = results["401999004"]
    assert (g4.clinched, g4.stage.title, g4.game_label) == (False, "World Series", "Game 4")
    assert (g4.winner, g4.loser, g4.winner_score, g4.loser_score) == ("CLE", "CHW", 9, 5)
    assert g4.series_summary == "CLE leads series 3-1" and g4.year == 2026
    clinch = next(r for r in results.values() if r.clinched)
    assert clinch.winner_name == "Cleveland Guardians" and clinch.winner_logo
    assert clinch.champion_text == "Cleveland Guardians vô địch World Series 2026"


def test_non_postseason_or_unfinished_is_ignored():
    regular = {**FIXTURE, "season": {"type": 2, "year": 2026}}
    assert parse_finals(regular, "MLB", STAGES) == []
    assert parse_finals({"season": {"type": 3, "year": 2026}, "events": [{"id": "1"}]}, "MLB", STAGES) == []


def test_clinch_only_stage_skips_game_results():
    data = json.loads(json.dumps(FIXTURE))
    for e in data["events"]:
        e["competitions"][0]["notes"][0]["headline"] = e["competitions"][0]["notes"][0]["headline"].replace(
            "World Series", "ALCS")
    results = parse_finals(data, "MLB", STAGES)
    assert [r.clinched for r in results] == [True]
    assert results[0].champion_text == "Cleveland Guardians vô địch American League 2026"


def test_single_game_final_is_a_clinch():
    data = json.loads(json.dumps(FIXTURE))
    event = data["events"][0]
    del event["competitions"][0]["series"]
    event["competitions"][0]["notes"][0]["headline"] = "World Series"
    [r] = [r for r in parse_finals({**data, "events": [event]}, "MLB", STAGES)]
    assert r.clinched is True and r.game_label is None


def test_config_file_loads():
    cfg = load_events_config()
    assert isinstance(cfg, EventsConfig)
    assert [lg.league for lg in cfg.leagues] == ["mlb", "nba", "nhl", "nfl"]
    assert cfg.leagues[0].stages[0].match == "World Series"
