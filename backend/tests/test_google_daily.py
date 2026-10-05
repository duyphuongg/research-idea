from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from app.connectors.base import RawBatch
from app.connectors.google_daily import RSS_URL, GoogleDailyTrendsConnector, parse_traffic

FIXTURE = Path(__file__).parent / "fixtures" / "google_daily" / "trending_us.xml"
TODAY = date(2026, 10, 5)


async def no_sleep(_seconds: float) -> None:
    return None


@pytest.mark.parametrize(
    "text,expected",
    [("200+", 200.0), ("50K+", 50000.0), ("2M+", 2000000.0), ("1,000+", 1000.0), ("lots", None), ("", None)],
)
def test_parse_traffic(text, expected):
    assert parse_traffic(text) == expected


def test_normalize_items_to_traffic_signals():
    raw = RawBatch(source="google_daily", payloads=[{"geo": "US", "xml": FIXTURE.read_text()}])
    signals = GoogleDailyTrendsConnector().normalize(raw, TODAY).signals
    assert [(s.keyword, s.value) for s in signals] == [
        ("braves dodgers game", 200.0),
        ("Halloween Costume Ideas", 50000.0),
        ("nurse appreciation week", 2000000.0),
    ]
    assert all(
        (s.source, s.metric, s.origin, s.parent, s.date) == ("google_daily", "traffic", "discovered", None, TODAY)
        for s in signals
    )


def test_normalize_skips_malformed_xml():
    raw = RawBatch(source="google_daily", payloads=[{"geo": "US", "xml": "<rss><broken"}])
    assert GoogleDailyTrendsConnector().normalize(raw, TODAY).signals == []


@respx.mock
async def test_fetch_us_feed_once():
    route = respx.get(url__startswith=RSS_URL).mock(return_value=httpx.Response(200, text=FIXTURE.read_text()))
    raw = await GoogleDailyTrendsConnector(sleep=no_sleep).fetch(["nurse", "dog mom"])
    assert route.call_count == 1
    assert route.calls[0].request.url.params["geo"] == "US"
    assert raw.payloads[0]["geo"] == "US" and "braves" in raw.payloads[0]["xml"]
    assert raw.errors == []


@respx.mock
async def test_fetch_error_is_collected():
    respx.get(url__startswith=RSS_URL).mock(return_value=httpx.Response(404))
    raw = await GoogleDailyTrendsConnector(sleep=no_sleep).fetch([])
    assert raw.payloads == [] and len(raw.errors) == 1
