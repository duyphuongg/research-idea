from datetime import date, timedelta

import httpx
import respx
from sqlalchemy import select

from app.connectors.etsy import BASE_URL
from app.keywords import get_or_create_keyword
from app.models import KeywordScore, ScanRun, TrendSignal
from app.pipeline.etsy_counts import pick_keywords, run_etsy_counts

TODAY = date(2026, 10, 9)


async def _no_sleep(_):
    return None


def _scored(session_factory):
    with session_factory() as s:
        ids = {}
        for text, score, pod in (("hockey mom", 80, True), ("ice hockey", 70, True),
                                 ("braves game", 90, False), ("fresh one", 60, True)):
            kw = get_or_create_keyword(s, text, origin="discovered", has_parent=True)
            kw.is_pod_relevant = pod
            s.add(KeywordScore(keyword_id=kw.id, score=score, date=TODAY, sources_rising=0, sources=[]))
            ids[text] = kw.id
        s.add(TrendSignal(keyword_id=ids["fresh one"], source="etsy", metric="listing_count_tshirt",
                          value=5, date=TODAY - timedelta(days=1)))
        s.commit()
        return ids


def test_pick_keywords_skips_non_pod_and_recently_counted(session_factory):
    ids = _scored(session_factory)
    with session_factory() as s:
        assert pick_keywords(s, TODAY) == [(ids["hockey mom"], "hockey mom"), (ids["ice hockey"], "ice hockey")]
        assert pick_keywords(s, TODAY, limit=1) == [(ids["hockey mom"], "hockey mom")]


@respx.mock
async def test_run_stores_counts_per_type(session_factory):
    ids = _scored(session_factory)

    def reply(request):
        query = request.url.params["keywords"]
        assert request.url.params["limit"] == "1"
        if query == "ice hockey hoodie":
            return httpx.Response(400, json={"error": "bad"})
        return httpx.Response(200, json={"count": len(query) * 100, "results": []})

    respx.get(f"{BASE_URL}/listings/active").mock(side_effect=reply)
    run_id = await run_etsy_counts(session_factory, "k", TODAY, min_interval=0, sleep=_no_sleep)

    with session_factory() as s:
        rows = {(r.keyword_id, r.metric): r.value for r in s.scalars(select(TrendSignal).where(TrendSignal.date == TODAY))}
        assert rows[(ids["hockey mom"], "listing_count_tshirt")] == len("hockey mom shirt") * 100
        assert rows[(ids["hockey mom"], "listing_count_hoodie")] == len("hockey mom hoodie") * 100
        assert (ids["ice hockey"], "listing_count_hoodie") not in rows
        assert (ids["ice hockey"], "listing_count_sweatshirt") in rows
        run = s.get(ScanRun, run_id)
        assert (run.source, run.status, run.records) == ("etsy_counts", "partial", 2)
        assert "ice hockey hoodie" in run.error


@respx.mock
async def test_run_stops_on_auth_error(session_factory):
    _scored(session_factory)
    route = respx.get(f"{BASE_URL}/listings/active").mock(return_value=httpx.Response(403, json={}))
    run_id = await run_etsy_counts(session_factory, "k", TODAY, min_interval=0, sleep=_no_sleep)
    assert route.call_count == 1
    with session_factory() as s:
        assert s.get(ScanRun, run_id).status == "failed"
