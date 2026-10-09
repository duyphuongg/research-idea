from datetime import date, datetime

from app.models import NflMoment, NflPerformance, NflPlayer, NflPlayerDemand
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
    session.add(NflMoment(query="player 2 touchdown", traffic=5000, first_seen=datetime(2026, 10, 8),
                          last_seen=datetime(2026, 10, 8), news=[], athlete_id="p2"))
    session.add(NflMoment(query="old p3 story", traffic=5000, first_seen=datetime(2026, 9, 1),
                          last_seen=datetime(2026, 9, 1), news=[], athlete_id="p3"))
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


def test_moments_api(client, session):
    session.add(NflPlayer(athlete_id="9", name="Jayden Daniels", first_name="Jayden", last_name="Daniels",
                          team="WSH", position="QB", updated_on=TODAY))
    from app.db import utcnow
    now = utcnow()
    session.add_all([
        NflMoment(query="small", traffic=1000, first_seen=now, last_seen=now, news=[]),
        NflMoment(query="jayden daniels injury", traffic=50000, first_seen=now, last_seen=now,
                  news=[{"title": "Knee injury", "url": "https://n/1", "source": "ESPN"}], athlete_id="9", team="WSH"),
        NflMoment(query="ancient", traffic=90000, first_seen=datetime(2026, 1, 1), last_seen=datetime(2026, 1, 1), news=[]),
    ])
    session.commit()
    items = client.get("/api/nfl/moments").json()["items"]
    assert [i["query"] for i in items] == ["jayden daniels injury", "small"]
    assert items[0]["player"]["name"] == "Jayden Daniels" and items[0]["news"][0]["source"] == "ESPN"
    assert items[1]["player"] is None
