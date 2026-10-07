import json
from datetime import date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from app.connectors.base import RawBatch
from app.connectors.etsy import EtsyConnector

FIXTURES = Path(__file__).parent / "fixtures" / "etsy"
SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
BATCH_URL = "https://openapi.etsy.com/v3/application/listings/batch"


def load_payload() -> dict:
    return json.loads((FIXTURES / "payload_nurse_shirt.json").read_text())


async def no_sleep(_seconds: float) -> None:
    return None


def test_enabled_requires_api_key():
    assert EtsyConnector("k").enabled() is True
    assert EtsyConnector(None).enabled() is False
    assert EtsyConnector("").enabled() is False


TODAY = date(2026, 10, 5)


def test_normalize_keeps_us_usd_apparel_only():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    batch = EtsyConnector("k").normalize(raw, TODAY)

    # 1002 mug (not apparel), 1004 non-US shop, 1005 CAD price are dropped
    assert [p.external_id for p in batch.products] == ["1001", "1003", "1006"]
    shirt, hoodie, crew = batch.products
    assert shirt.title == "Funny Nurse Shirt & Gift"
    assert shirt.price == 24.99
    assert shirt.currency == "USD"
    assert shirt.favorites == 532
    assert shirt.views == 1200
    assert shirt.shop_sold_count == 15400
    assert shirt.image_url == "https://i.etsystatic.com/1001_570xN.jpg"
    assert shirt.shop_name == "NurseLifeCo"
    assert shirt.product_type == "tshirt"
    assert shirt.listed_at == datetime(2025, 8, 1)
    assert (shirt.keyword, shirt.rank) == ("nurse", 1)
    assert (hoodie.product_type, hoodie.rank, hoodie.image_url) == ("hoodie", 3, None)
    assert (crew.product_type, crew.rank) == ("sweatshirt", 6)


def test_normalize_emits_keyword_signals_and_tags():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    signals = EtsyConnector("k").normalize(raw, TODAY).signals
    by_metric = {(s.source, s.metric, s.keyword): s for s in signals}

    assert by_metric[("etsy", "listing_count_tshirt", "nurse")].value == 12345.0
    assert by_metric[("etsy", "us_listing_count", "nurse")].value == 3.0
    assert by_metric[("etsy", "new_listings_30d", "nurse")].value == 2.0
    expected_rate = (1200 / 430 + 300 / 15 + 60 / 15) / 3
    assert by_metric[("etsy", "views_per_day", "nurse")].value == pytest.approx(expected_rate)

    tags = {s.keyword: s for s in signals if s.source == "etsy_tags"}
    assert set(tags) == {"nurse gift", "rn shirt"}  # only tags on >= 3 kept US listings
    gift = tags["nurse gift"]
    assert (gift.metric, gift.value, gift.origin, gift.parent, gift.date) == (
        "tag_count", 3.0, "discovered", "nurse", TODAY
    )
    assert all(s.date == TODAY for s in signals)


def test_keyword_signals_dedupe_listings_across_queries():
    payload = load_payload()
    second = {**payload, "query": "nurse hoodie", "product_type": "hoodie"}
    raw = RawBatch(source="etsy", payloads=[payload, second])
    signals = EtsyConnector("k").normalize(raw, TODAY).signals
    us_count = [s for s in signals if s.metric == "us_listing_count"]
    assert [s.value for s in us_count] == [3.0]
    assert {s.metric for s in signals if s.metric.startswith("listing_count_")} == {
        "listing_count_tshirt", "listing_count_hoodie"
    }


@respx.mock
async def test_fetch_runs_search_and_batch_per_product_type():
    payload = load_payload()
    search = respx.get(url__startswith=SEARCH_URL).mock(
        return_value=httpx.Response(200, json=payload["search"])
    )
    batch = respx.get(url__startswith=BATCH_URL).mock(
        return_value=httpx.Response(200, json=payload["details"])
    )

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert [p["query"] for p in raw.payloads] == ["nurse shirt", "nurse sweatshirt", "nurse hoodie"]
    assert [p["product_type"] for p in raw.payloads] == ["tshirt", "sweatshirt", "hoodie"]
    assert raw.errors == []
    assert search.call_count == 3
    assert batch.call_count == 3
    first = search.calls[0].request
    assert first.headers["x-api-key"] == "k"
    assert first.url.params["keywords"] == "nurse shirt"
    assert batch.calls[0].request.url.params["listing_ids"] == "1001,1002,1003,1004,1005,1006"
    assert first.url.params["limit"] == "100"


@respx.mock
async def test_fetch_collects_errors_per_query():
    respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404, text="nope"))

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert raw.payloads == []
    assert len(raw.errors) == 3
    assert all("HTTP 404" in e for e in raw.errors)


@respx.mock
async def test_fetch_treats_unparseable_body_as_query_error():
    respx.get(url__startswith=SEARCH_URL).mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>")
    )

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert raw.payloads == []
    assert len(raw.errors) == 3


def test_normalize_skips_listings_without_id():
    payload = {
        "keyword": "nurse",
        "query": "nurse shirt",
        "product_type": "tshirt",
        "search": {
            "count": 2,
            "results": [
                {"title": "Broken Shirt"},
                {"listing_id": 7, "title": "Nurse Shirt", "price": {"amount": 2000, "divisor": 100, "currency_code": "USD"}},
            ],
        },
        "details": {"results": [{"title": "Broken Detail Shirt"}, {"listing_id": 7, "shop": {"is_shop_us_based": True}}]},
    }
    batch = EtsyConnector("k").normalize(RawBatch(source="etsy", payloads=[payload]), date(2026, 10, 5))

    assert [p.external_id for p in batch.products] == ["7"]


def test_normalize_fills_normalized_tags():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    shirt = EtsyConnector("k").normalize(raw, TODAY).products[0]
    assert shirt.tags == ["nurse shirt", "nurse gift", "funny nurse", "rn shirt"]
