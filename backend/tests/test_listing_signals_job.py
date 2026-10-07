from datetime import date

import httpx
import respx
from sqlalchemy import select

from app.analysis.listing_signals import SignalsConfig
from app.models import ListingSignal, Product, ScanRun, TrendSignal
from app.pipeline.listing_signals import EtsySignalsClient, run_listing_signals

SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
BATCH_URL = "https://openapi.etsy.com/v3/application/listings/batch"
DAY1, DAY2 = date(2026, 10, 6), date(2026, 10, 7)
OCT1 = 1790812800  # 2026-10-01 UTC
OLD = 1754006400  # 2025-08-01 UTC
US = {"shop_id": 1, "shop_name": "UsShop", "is_shop_us_based": True, "transaction_sold_count": 50}
CONFIG = SignalsConfig(queries=("shirt",), pages_per_query=1)


async def no_sleep(_):
    return None


def client_factory(key):
    return EtsySignalsClient(key, min_interval=0, sleep=no_sleep)


def listing(lid, title, views, saves, tags, created=OCT1, shop=US, currency="USD"):
    return {
        "listing_id": lid, "title": title, "views": views, "num_favorers": saves, "tags": tags,
        "price": {"amount": 2500, "divisor": 100, "currency_code": currency},
        "url": f"https://www.etsy.com/listing/{lid}", "original_creation_timestamp": created,
        "images": [{"url_570xN": f"https://img/{lid}.jpg"}], "shop": shop,
    }


def day(views_501, saves_501, views_502, saves_502):
    details = [
        listing(501, "Vintage Sasquatch Shirt", views_501, saves_501, ["vintage sasquatch", "funny cryptid"]),
        listing(502, "Sasquatch Camping Tee", views_502, saves_502, ["Vintage Sasquatch", "camping shirt"]),
        listing(503, "Old Shirt", 10, 1, ["old"], created=OLD),
        listing(504, "Foreign Shirt", 10, 1, ["x"], shop={**US, "is_shop_us_based": False}),
    ]
    search = {"count": 4, "results": [{k: d[k] for k in ("listing_id", "original_creation_timestamp")} for d in details]}
    return search, {"count": 4, "results": details}


async def run_day(session_factory, today, data):
    search, batch = data
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search))
        respx.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(200, json=batch))
        return await run_listing_signals(
            session_factory, "k", [], today, config=CONFIG, client_factory=client_factory
        )


async def test_two_days_classify_and_emit_tag_signals(session_factory):
    run1 = await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    with session_factory() as s:
        assert s.get(ScanRun, run1).status == "ok"
        signals = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert set(signals) == {"501", "502"}  # old and non-US skipped
        assert {r.status for r in signals.values()} == {"calibrating"}
        assert signals["501"].discovery_query == "shirt"
        assert s.scalars(select(TrendSignal)).all() == []

    await run_day(session_factory, DAY2, day(160, 22, 80, 4))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["501"].status == "super_breakout"
        assert (rows["501"].delta_saves, round(rows["501"].dsr, 2), rows["501"].age_days) == (12.0, 0.2, 6)
        assert rows["502"].status == "steady_grower"
        assert s.get(Product, rows["501"].product_id).tags == ["vintage sasquatch", "funny cryptid"]
        tags = {(t.source, t.metric, t.value) for t in s.scalars(select(TrendSignal))}
        assert tags == {("etsy_signals", "breakout_tag_count", 2.0)}  # only "vintage sasquatch" on >= 2


async def test_search_failure_is_partial_and_isolated(session_factory):
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404))
        run_id = await run_listing_signals(
            session_factory, "k", ["nurse"], DAY1, config=CONFIG, client_factory=client_factory
        )
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "HTTP 404" in run.error
        assert run.source == "etsy_signals"
