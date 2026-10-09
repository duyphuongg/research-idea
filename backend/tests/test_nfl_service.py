from datetime import date, datetime

from app.keywords import get_or_create_keyword
from app.models import NflPerformance, NflPlayerDemand, TrendSignal
from app.services.nfl import potential, standouts

TODAY = date(2026, 10, 9)


def _perf(session, week, event, aid, name, category, points, line="1 TD"):
    session.add(NflPerformance(season=2026, season_type=2, week=week, event_id=event, game=f"G{event}",
                               game_date=datetime(2026, 10, 5), athlete_id=aid, name=name, position="QB",
                               jersey="4", team="DAL", category=category, stat_line=line, points=points))


def test_potential():
    assert potential(1.0, 10, 9999, False) == 100.0
    assert potential(0.0, None, None, False) == 0.0
    assert potential(0.5, 5, 99, True) == 25 + 15 + 10 + 10
    assert potential(1.0, 10, 99999, True) == 100.0


def test_standouts_default_week_and_ranking(session):
    for e in range(10):  # week 4 complete
        _perf(session, 4, f"a{e}", f"p{e}", f"Player {e}", "passingYards", float(e))
    _perf(session, 5, "b0", "x", "Thursday Guy", "rushingYards", 30)  # week 5 just started
    _perf(session, 4, "a9", "p9", "Player 9", "rushingYards", 5, "10 YDS")  # two lines, same game
    session.add(NflPlayerDemand(athlete_id="p1", date=date(2026, 10, 7), etsy_listings=10, merch_suggestions=1))
    session.add(NflPlayerDemand(athlete_id="p1", date=TODAY, etsy_listings=9999, merch_suggestions=10))
    kw = get_or_create_keyword(session, "player 2 touchdown", origin="discovered")
    session.add(TrendSignal(keyword_id=kw.id, source="google_daily", metric="traffic", value=1, date=TODAY))
    session.flush()

    page = standouts(session, today=TODAY)
    assert (page["season"], page["season_type"], page["week"]) == (2026, 2, 4)
    assert [w["week"] for w in page["weeks"]] == [5, 4] and page["weeks"][1]["games"] == 10
    items = {i["athlete_id"]: i for i in page["items"]}
    assert items["p9"]["points"] == 14 and len(items["p9"]["lines"]) == 2 and items["p9"]["games"] == ["Ga9"]
    assert items["p1"]["etsy_listings"] == 9999 and items["p1"]["merch_suggestions"] == 10
    assert items["p2"]["trending"] is True and items["p3"]["trending"] is False
    assert page["items"][0]["athlete_id"] == "p1"  # demand outweighs a few points
    assert items["p0"]["potential"] == 0.0

    week5 = standouts(session, week=5, today=TODAY)
    assert week5["week"] == 5 and [i["name"] for i in week5["items"]] == ["Thursday Guy"]
    assert standouts(session, week=9, today=TODAY)["items"] == []


def test_api(client, session):
    assert client.get("/api/nfl/standouts").json() == {
        "season": None, "season_type": None, "week": None, "weeks": [], "items": []}
    _perf(session, 3, "e", "p", "Some One", "receivingYards", 12.5)
    session.commit()
    body = client.get("/api/nfl/standouts").json()
    assert body["week"] == 3 and body["items"][0]["name"] == "Some One"
    assert client.get("/api/nfl/standouts?week=0").status_code == 422
