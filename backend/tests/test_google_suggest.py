import json
from datetime import date
from pathlib import Path

import httpx
import respx

from app.connectors.base import RawBatch
from app.connectors.google_suggest import SUGGEST_URL, GoogleSuggestConnector

FIXTURE = Path(__file__).parent / "fixtures" / "google_suggest" / "nurse_shirt.json"
TODAY = date(2026, 10, 5)


async def no_sleep(_seconds: float) -> None:
    return None


def suggestions() -> list[str]:
    return json.loads(FIXTURE.read_text())[1]


def test_always_enabled_trend_source():
    c = GoogleSuggestConnector()
    assert (c.name, c.kind, c.enabled()) == ("google_suggest", "trend", True)


def test_normalize_scores_suggestions_by_rank():
    raw = RawBatch(source="google_suggest", payloads=[
        {"keyword": "nurse", "query": "nurse shirt", "suggestions": suggestions()}
    ])
    signals = GoogleSuggestConnector().normalize(raw, TODAY).signals

    assert len(signals) == 10
    first = signals[0]
    assert (first.keyword, first.source, first.metric, first.value) == (
        "nurse shirts", "google_suggest", "suggest_score", 10.0
    )
    assert (first.origin, first.parent, first.date) == ("discovered", "nurse", TODAY)
    assert signals[-1].keyword == "nurse shirt png" and signals[-1].value == 1.0


def test_normalize_keeps_best_rank_and_skips_query_echo():
    raw = RawBatch(source="google_suggest", payloads=[
        {"keyword": "nurse", "query": "nurse shirt", "suggestions": ["nurse shirt", "a", "nurse gift"]},
        {"keyword": "nurse", "query": "nurse hoodie", "suggestions": ["nurse gift"]},
    ])
    signals = {s.keyword: s.value for s in GoogleSuggestConnector().normalize(raw, TODAY).signals}
    assert signals == {"a": 9.0, "nurse gift": 10.0}


@respx.mock
async def test_fetch_queries_us_suggestions_per_suffix():
    route = respx.get(url__startswith=SUGGEST_URL).mock(
        return_value=httpx.Response(200, content=FIXTURE.read_bytes(), headers={"content-type": "application/json"})
    )
    raw = await GoogleSuggestConnector(min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert [p["query"] for p in raw.payloads] == ["nurse shirt", "nurse hoodie", "nurse sweatshirt"]
    assert raw.payloads[0]["suggestions"][0] == "nurse shirts"
    assert raw.errors == []
    params = route.calls[0].request.url.params
    assert (params["client"], params["hl"], params["gl"], params["q"]) == ("firefox", "en", "us", "nurse shirt")


@respx.mock
async def test_fetch_collects_errors():
    respx.get(url__startswith=SUGGEST_URL).mock(return_value=httpx.Response(200, text="not json"))
    raw = await GoogleSuggestConnector(min_interval=0, sleep=no_sleep).fetch(["nurse"])
    assert raw.payloads == []
    assert len(raw.errors) == 3
