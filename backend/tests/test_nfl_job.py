import json
from datetime import date
from pathlib import Path

import httpx
import respx
from sqlalchemy import func, select

from app.connectors.espn_nfl import SCOREBOARD_URL
from app.connectors.etsy import BASE_URL as ETSY_URL
from app.connectors.google_suggest import SUGGEST_URL
from app.models import NflPerformance, NflPlayerDemand, ScanRun
from app.pipeline.nfl import run_nfl

TODAY = date(2026, 10, 9)
FIXTURE = json.loads((Path(__file__).parent / "fixtures/espn/scoreboard.json").read_text())


async def _no_sleep(_):
    return None


def _previous_week():
    data = json.loads(json.dumps(FIXTURE))
    data["week"]["number"] = 4
    data["events"][0]["id"] = "prev1"
    return data


@respx.mock
async def test_run_stores_weeks_and_demand(session_factory):
    def scoreboard(request):
        return httpx.Response(200, json=_previous_week() if request.url.params.get("week") == "4" else FIXTURE)

    respx.get(SCOREBOARD_URL).mock(side_effect=scoreboard)
    etsy = respx.get(f"{ETSY_URL}/listings/active").mock(return_value=httpx.Response(200, json={"count": 1234}))
    respx.get(SUGGEST_URL).mock(side_effect=lambda r: httpx.Response(
        200, json=[r.url.params["q"], [r.url.params["q"], "x shirtless", "x jersey youth", "x age"]]))

    run_id = await run_nfl(session_factory, "key", TODAY, min_interval=0, sleep=_no_sleep)
    run_id_again = await run_nfl(session_factory, "key", TODAY, min_interval=0, sleep=_no_sleep)

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(NflPerformance)) == 6  # 3 per week, rerun replaces
        assert {w for (w,) in s.execute(select(NflPerformance.week).distinct())} == {4, 5}
        demand = s.scalars(select(NflPlayerDemand)).all()
        assert len(demand) == 3 and {(d.etsy_listings, d.merch_suggestions) for d in demand} == {(1234, 2)}
        assert etsy.calls[0].request.headers["x-api-key"] == "key"
        assert etsy.call_count == 3  # second run: demand is fresh
        assert s.get(ScanRun, run_id).status == "ok" and s.get(ScanRun, run_id_again).records == 6


@respx.mock
async def test_without_etsy_key_only_google(session_factory):
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(200, json=FIXTURE))
    etsy = respx.get(f"{ETSY_URL}/listings/active")
    respx.get(SUGGEST_URL).mock(return_value=httpx.Response(200, json=["q", ["a shirt"]]))
    await run_nfl(session_factory, None, TODAY, min_interval=0, sleep=_no_sleep)
    assert etsy.call_count == 0
    with session_factory() as s:
        assert {(d.etsy_listings, d.merch_suggestions) for d in s.scalars(select(NflPlayerDemand))} == {(None, 1)}


@respx.mock
async def test_espn_down_fails_the_run_only(session_factory):
    respx.get(SCOREBOARD_URL).mock(return_value=httpx.Response(404))
    run_id = await run_nfl(session_factory, "key", TODAY, min_interval=0, sleep=_no_sleep)
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "404" in run.error
