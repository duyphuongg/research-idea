import json
from datetime import date, datetime
from pathlib import Path

import httpx
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


def test_normalize_maps_apparel_listings_and_drops_others():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    batch = EtsyConnector("k").normalize(raw, date(2026, 10, 5))

    assert [p.external_id for p in batch.products] == ["1001", "1003"]
    shirt, hoodie = batch.products
    assert shirt.title == "Funny Nurse Shirt & Gift"
    assert shirt.price == 24.99
    assert shirt.currency == "USD"
    assert shirt.favorites == 532
    assert shirt.reviews is None
    assert shirt.image_url == "https://i.etsystatic.com/1001_570xN.jpg"
    assert shirt.shop_name == "NurseLifeCo"
    assert shirt.product_type == "tshirt"
    assert shirt.listed_at == datetime(2025, 8, 1)
    assert shirt.keyword == "nurse"
    assert shirt.rank == 1
    assert hoodie.product_type == "hoodie"
    assert hoodie.rank == 3
    assert hoodie.image_url is None
    assert hoodie.listed_at is not None

    assert len(batch.signals) == 1
    signal = batch.signals[0]
    assert (signal.keyword, signal.source, signal.metric, signal.value, signal.date) == (
        "nurse", "etsy", "listing_count_tshirt", 12345.0, date(2026, 10, 5)
    )


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
    assert batch.calls[0].request.url.params["listing_ids"] == "1001,1002,1003"


@respx.mock
async def test_fetch_collects_errors_per_query():
    respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404, text="nope"))

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert raw.payloads == []
    assert len(raw.errors) == 3
    assert all("HTTP 404" in e for e in raw.errors)
