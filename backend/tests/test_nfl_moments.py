from datetime import date, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from app.connectors.etsy import BASE_URL as ETSY_URL
from app.connectors.google_daily import RSS_URL
from app.models import NflMoment, NflPlayer, ScanRun, SportsTeam
from app.pipeline.nfl_moments import ESPN_TEAMS_URL, TEAM_LEAGUES, TEAMS_URL, parse_rss, run_nfl_moments

NOW = datetime(2026, 10, 9, 10, 30)
RSS = (Path(__file__).parent / "fixtures/google_trends/nfl_rss.xml").read_text()
TEAMS = {"sports": [{"leagues": [{"teams": [{"team": {"id": "28", "abbreviation": "WSH"}}]}]}]}
ROSTER = {"athletes": [{"position": "offense", "items": [
    {"id": "4426348", "firstName": "Jayden", "lastName": "Daniels", "displayName": "Jayden Daniels",
     "position": {"abbreviation": "QB"}, "jersey": "5", "headshot": {"href": "https://h/jd.png"}},
    {"id": "x"},  # incomplete entries are skipped
]}]}


async def _no_sleep(_):
    return None


def test_parse_rss():
    trends = parse_rss(RSS)
    assert [t.query for t in trends] == ["jayden daniels injury", "cowboys", "openai"]
    jd = trends[0]
    assert jd.traffic == 50000 and jd.picture_url == "https://img/jd.jpg"
    assert jd.published == datetime(2026, 10, 9, 9, 0)
    assert jd.news[0] == {"title": "Jayden Daniels leaves game with knee injury", "url": "https://news/1", "source": "ESPN"}
    assert trends[1].traffic == 10000


LEAGUE_TEAMS = {"sports": [{"leagues": [{"teams": [
    {"team": {"id": "1", "abbreviation": "NYY", "displayName": "New York Yankees", "name": "Yankees"}}]}]}]}


def _mock_league_teams():
    for sport, league in TEAM_LEAGUES[1:]:
        respx.get(TEAMS_URL.format(sport=sport, league=league)).mock(
            return_value=httpx.Response(200, json=LEAGUE_TEAMS))


@respx.mock
async def test_run_refreshes_rosters_and_stores_nfl_trends_only(session_factory):
    respx.get(ESPN_TEAMS_URL).mock(return_value=httpx.Response(200, json={"sports": [{"leagues": [{"teams": [
        {"team": {"id": "28", "abbreviation": "WSH", "displayName": "Washington Commanders", "name": "Commanders"}}]}]}]}))
    _mock_league_teams()
    roster = respx.get(f"{ESPN_TEAMS_URL}/28/roster").mock(return_value=httpx.Response(200, json=ROSTER))
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, text=RSS))
    etsy = respx.get(f"{ETSY_URL}/listings/active").mock(return_value=httpx.Response(200, json={"count": 42}))

    run_id = await run_nfl_moments(session_factory, "key", now=NOW, min_interval=0, sleep=_no_sleep)
    later = datetime(2026, 10, 9, 11, 30)
    await run_nfl_moments(session_factory, "key", now=later, min_interval=0, sleep=_no_sleep)

    with session_factory() as s:
        assert s.get(NflPlayer, "4426348").team == "WSH" and s.get(NflPlayer, "x") is None
        teams = {(t.league, t.full_name, t.nickname) for t in s.scalars(select(SportsTeam))}
        assert ("nfl", "Washington Commanders", "Commanders") in teams and ("mlb", "New York Yankees", "Yankees") in teams
        moments = {m.query: m for m in s.scalars(select(NflMoment))}
        assert set(moments) == {"jayden daniels injury", "cowboys"}
        jd = moments["jayden daniels injury"]
        assert (jd.athlete_id, jd.team, jd.traffic, jd.etsy_listings) == ("4426348", "WSH", 50000, 42)
        assert jd.first_seen == NOW and jd.last_seen == later and len(jd.news) == 2
        assert (moments["cowboys"].athlete_id, moments["cowboys"].team) == (None, "DAL")
        assert roster.call_count == 1  # rosters are fresh on the second run
        assert etsy.call_count == 2  # only on first sight
        assert etsy.calls[0].request.headers["x-api-key"] == "key"
        run = s.get(ScanRun, run_id)
        assert (run.source, run.status, run.records) == ("nfl_moments", "ok", 2)


@respx.mock
async def test_roster_failure_still_reads_trends(session_factory):
    respx.get(ESPN_TEAMS_URL).mock(return_value=httpx.Response(500))
    respx.get(RSS_URL).mock(return_value=httpx.Response(200, text=RSS))
    run_id = await run_nfl_moments(session_factory, None, now=NOW, min_interval=0, sleep=_no_sleep)
    with session_factory() as s:
        assert {m.query for m in s.scalars(select(NflMoment))} == {"cowboys"}  # no roster: player unknown
        assert s.get(ScanRun, run_id).status == "partial"


@respx.mock
async def test_rss_down(session_factory):
    _mock_league_teams()
    respx.get(ESPN_TEAMS_URL).mock(return_value=httpx.Response(200, json={"sports": [{"leagues": [{"teams": []}]}]}))
    respx.get(RSS_URL).mock(return_value=httpx.Response(404))
    run_id = await run_nfl_moments(session_factory, None, now=NOW, min_interval=0, sleep=_no_sleep)
    with session_factory() as s:
        assert s.get(ScanRun, run_id).status == "failed"
