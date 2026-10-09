from datetime import date

import httpx
import pytest
import respx
from sqlalchemy import select

from app.analysis.listing_signals import SignalsConfig
from app.connectors.base import ConnectorError
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


async def test_all_queries_failing_marks_run_failed(session_factory):
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404))
        run_id = await run_listing_signals(
            session_factory, "k", ["nurse"], DAY1, config=CONFIG, client_factory=client_factory
        )
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "HTTP 404" in run.error
        assert run.source == "etsy_signals"


def search_of(details):
    return {"results": [{k: d[k] for k in ("listing_id", "original_creation_timestamp")} for d in details]}


def requested_ids(call):
    return set(call.request.url.params["listing_ids"].split(","))


async def test_gone_listing_marked_and_not_requested_again(session_factory):
    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    search, batch = day(160, 22, 80, 4)
    batch = {"results": [d for d in batch["results"] if d["listing_id"] != 502]}
    await run_day(session_factory, DAY2, (search, batch))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["502"].status == "gone" and rows["502"].updated_on == DAY2
        assert rows["501"].status != "gone"
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search))
        route = respx.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(200, json=batch))
        await run_listing_signals(
            session_factory, "k", [], date(2026, 10, 8), config=CONFIG, client_factory=client_factory
        )
    assert all("502" not in requested_ids(c) for c in route.calls)


async def test_listing_turning_non_us_becomes_gone(session_factory):
    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    search, batch = day(160, 22, 80, 4)
    for d in batch["results"]:
        if d["listing_id"] == 502:
            d["shop"] = {**US, "is_shop_us_based": False}
    await run_day(session_factory, DAY2, (search, batch))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["502"].status == "gone"


async def test_tracked_digital_download_becomes_gone(session_factory):
    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    search, batch = day(160, 22, 80, 4)
    for d in batch["results"]:
        if d["listing_id"] == 502:
            d["listing_type"] = "download"
    await run_day(session_factory, DAY2, (search, batch))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["502"].status == "gone"
        assert rows["501"].status != "gone"


async def test_failing_chunk_is_bisected_and_run_partial(session_factory):
    details = [listing(i, f"Shirt {i}", 10, 1, ["t"]) for i in (601, 666, 602, 603)]

    def batch_handler(request):
        if "666" in request.url.params["listing_ids"].split(","):
            return httpx.Response(404)
        wanted = request.url.params["listing_ids"].split(",")
        return httpx.Response(200, json={"results": [d for d in details if str(d["listing_id"]) in wanted]})

    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search_of(details)))
        respx.get(url__startswith=BATCH_URL).mock(side_effect=batch_handler)
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=CONFIG, client_factory=client_factory
        )
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "partial" and "666" in run.error
        ids = {s.get(Product, r.product_id).external_id for r in s.scalars(select(ListingSignal))}
        assert ids == {"601", "602", "603"}


async def test_one_query_failing_is_partial(session_factory):
    details = [listing(701, "Good Shirt", 10, 1, ["t"])]
    config = SignalsConfig(queries=("bad", "shirt"), pages_per_query=1)

    def search_handler(request):
        if request.url.params["keywords"] == "bad":
            return httpx.Response(404)
        return httpx.Response(200, json=search_of(details))

    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(side_effect=search_handler)
        respx.get(url__startswith=BATCH_URL).mock(
            return_value=httpx.Response(200, json={"results": details})
        )
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=config, client_factory=client_factory
        )
    with session_factory() as s:
        assert s.get(ScanRun, run_id).status == "partial"
        assert len(s.scalars(select(ListingSignal)).all()) == 1


async def test_search_new_stops_when_page_is_short():
    with respx.mock:
        route = respx.get(url__startswith=SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": [{"listing_id": 1}] * 99})
        )
        async with client_factory("k") as client:
            results = await client.search_new("shirt", 3)
    assert route.call_count == 1 and len(results) == 99


async def test_max_tracked_caps_new_discoveries(session_factory):
    config = SignalsConfig(queries=("shirt",), pages_per_query=1, max_tracked=1)
    details = [listing(801, "A Shirt", 10, 1, ["t"]), listing(802, "B Shirt", 10, 1, ["t"])]
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search_of(details)))
        route = respx.get(url__startswith=BATCH_URL).mock(
            return_value=httpx.Response(200, json={"results": details})
        )
        await run_listing_signals(session_factory, "k", [], DAY1, config=config, client_factory=client_factory)
    assert all(requested_ids(c) == {"801"} for c in route.calls)
    with session_factory() as s:
        ids = {s.get(Product, r.product_id).external_id for r in s.scalars(select(ListingSignal))}
        assert ids == {"801"}


async def test_unexpected_response_shape_raises_connector_error():
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=[1]))
        async with client_factory("k") as client:
            with pytest.raises(ConnectorError, match="unexpected response shape"):
                await client.search_new("shirt", 1)
        respx.get(url__startswith=SEARCH_URL).mock(
            return_value=httpx.Response(200, json={"results": "nope"})
        )
        async with client_factory("k") as client:
            with pytest.raises(ConnectorError, match="unexpected response shape"):
                await client.search_new("shirt", 1)


async def test_persisted_only_first_image_kept():
    from app.pipeline.listing_signals import trim_images

    item = {"listing_id": 1, "images": [{"a": 1}, {"a": 2}]}
    assert trim_images(item)["images"] == [{"a": 1}]


def many_details(n):
    return [listing(1000 + i, f"Shirt {i}", 10, 1, ["t"]) for i in range(n)]


def paged_search(details):
    def handler(request):
        off = int(request.url.params["offset"])
        return httpx.Response(200, json=search_of(details[off : off + 100]))

    return handler


async def test_batch_503_is_bounded_and_not_bisected(session_factory):
    details = many_details(500)
    config = SignalsConfig(queries=("shirt",), pages_per_query=5)
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(side_effect=paged_search(details))
        route = respx.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(503))
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=config, client_factory=client_factory
        )
    assert route.call_count <= 3 * 4  # 3 chunks x (1 try + 3 retries)
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status in ("failed", "partial")
        assert "aborted after 3 consecutive failed batches" in run.error


async def test_batch_403_fails_fast(session_factory):
    details = many_details(300)
    config = SignalsConfig(queries=("shirt",), pages_per_query=3)
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(side_effect=paged_search(details))
        route = respx.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(403))
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=config, client_factory=client_factory
        )
    assert route.call_count == 1
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "HTTP 403" in run.error


async def test_empty_batch_response_marks_nothing_gone(session_factory):
    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    search, _ = day(160, 22, 80, 4)
    await run_day(session_factory, DAY2, (search, {"results": []}))
    with session_factory() as s:
        assert {r.status for r in s.scalars(select(ListingSignal))} == {"calibrating"}


async def test_detail_missing_shop_is_not_marked_gone(session_factory):
    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    search, batch = day(160, 22, 80, 4)
    for d in batch["results"]:
        if d["listing_id"] == 502:
            del d["shop"]
    await run_day(session_factory, DAY2, (search, batch))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["502"].status != "gone"


async def test_search_401_fails_fast(session_factory):
    config = SignalsConfig(queries=("a", "b", "c"), pages_per_query=1)
    with respx.mock:
        route = respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(401))
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=config, client_factory=client_factory
        )
    assert route.call_count == 1
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "HTTP 401" in run.error


async def test_search_aborts_after_three_consecutive_failures(session_factory):
    config = SignalsConfig(queries=("a", "b", "c", "d", "e"), pages_per_query=1)
    with respx.mock:
        route = respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404))
        run_id = await run_listing_signals(
            session_factory, "k", [], DAY1, config=config, client_factory=client_factory
        )
    assert route.call_count == 3
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed"
        assert "search aborted after 3 consecutive failed queries" in run.error


async def test_tag_counts_use_canonical_form(session_factory):
    details = [
        listing(801, "A Shirt", 10, 1, ["funny shirt"]),
        listing(802, "B Shirt", 10, 1, ["Funny Shirts"]),
    ]
    day1 = ({"results": [{k: d[k] for k in ("listing_id", "original_creation_timestamp")} for d in details]},
            {"results": details})
    await run_day(session_factory, DAY1, day1)
    bumped = [{**details[0], "views": 400, "num_favorers": 60}, {**details[1], "views": 400, "num_favorers": 60}]
    await run_day(session_factory, DAY2, (day1[0], {"results": bumped}))
    with session_factory() as s:
        sigs = s.scalars(select(TrendSignal)).all()
        assert [(t.value) for t in sigs] == [2.0]


async def test_tracked_only_snapshots_pruned(session_factory):
    from datetime import timedelta

    from app.models import ProductKeyword, ProductSnapshot
    from app.keywords import get_or_create_keyword

    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    old = DAY2 - timedelta(days=CONFIG.track_days + 8)
    recent = DAY2 - timedelta(days=CONFIG.track_days)
    with session_factory() as s:
        tracked_pid = s.scalars(select(Product.id).where(Product.external_id == "501")).one()
        other = Product(source="etsy", external_id="900", title="x", url="u", product_type="tshirt")
        s.add(other)
        s.flush()
        kw = get_or_create_keyword(s, "nurse")
        s.add(ProductKeyword(product_id=other.id, keyword_id=kw.id, rank=1, last_seen=DAY1))
        for pid in (tracked_pid, other.id):
            s.add(ProductSnapshot(product_id=pid, date=old, favorites=1))
            s.add(ProductSnapshot(product_id=pid, date=recent, favorites=1))
        s.commit()
    await run_day(session_factory, DAY2, day(160, 22, 80, 4))
    with session_factory() as s:
        dates = lambda pid: {x.date for x in s.scalars(select(ProductSnapshot).where(ProductSnapshot.product_id == pid))}
        assert old not in dates(tracked_pid) and recent in dates(tracked_pid)
        assert old in dates(other.id)


async def test_job_records_us_shops_and_daily_snapshots(session_factory):
    from app.models import Shop, ShopSnapshot

    await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    await run_day(session_factory, DAY2, day(160, 22, 80, 4))
    with session_factory() as s:
        shops = s.scalars(select(Shop)).all()
        assert [(sh.id, sh.name, sh.first_seen, sh.last_seen) for sh in shops] == [(1, "UsShop", DAY1, DAY2)]
        snaps = s.scalars(select(ShopSnapshot).order_by(ShopSnapshot.date)).all()
        assert [(sn.date, sn.sold_count) for sn in snaps] == [(DAY1, 50), (DAY2, 50)]
        products = s.scalars(select(Product)).all()
        assert products and {p.shop_id for p in products} == {1}


SHOP_URL = "https://openapi.etsy.com/v3/application/shops"


def shop_payload(shop_id, sold, us=True, name=None):
    return {"shop_id": shop_id, "shop_name": name or f"Shop{shop_id}", "is_shop_us_based": us,
            "url": f"https://www.etsy.com/shop/S{shop_id}", "icon_url_fullxfull": f"https://img/s{shop_id}.jpg",
            "transaction_sold_count": sold, "num_favorers": 9, "listing_active_count": 20,
            "review_average": 4.9, "review_count": 33}


async def test_watched_shops_refreshed_after_tracking(session_factory, caplog):
    from datetime import datetime as dt

    from app.models import Shop, ShopSnapshot

    with session_factory() as s:
        for sid, watched in ((7, True), (8, True), (9, True), (10, False)):
            s.add(Shop(id=sid, name=f"Old{sid}", first_seen=DAY1, last_seen=DAY1,
                       watched_at=dt(2026, 10, 1) if watched else None))
        s.commit()
    search, batch = day(100, 10, 50, 2)
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search))
        mock.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(200, json=batch))
        ok = mock.get(f"{SHOP_URL}/7").mock(return_value=httpx.Response(200, json=shop_payload(7, 1234)))
        bad = mock.get(f"{SHOP_URL}/8").mock(return_value=httpx.Response(404, json={"error": "gone"}))
        foreign = mock.get(f"{SHOP_URL}/9").mock(return_value=httpx.Response(200, json=shop_payload(9, 5, us=False)))
        unwatched = mock.get(f"{SHOP_URL}/10").mock(return_value=httpx.Response(200, json=shop_payload(10, 5)))
        with caplog.at_level("WARNING"):
            run_id = await run_listing_signals(
                session_factory, "k", [], DAY2, config=CONFIG, client_factory=client_factory
            )
    assert ok.call_count == 1 and bad.call_count == 1 and foreign.call_count == 1
    assert unwatched.call_count == 0
    assert ok.calls[0].request.headers["x-api-key"] == "k"
    assert "shop 8" in caplog.text
    with session_factory() as s:
        assert s.get(ScanRun, run_id).status == "ok"
        seven = s.get(Shop, 7)
        assert (seven.name, seven.icon_url, seven.last_seen) == ("Shop7", "https://img/s7.jpg", DAY2)
        snap = s.scalars(select(ShopSnapshot).where(ShopSnapshot.shop_id == 7)).one()
        assert (snap.date, snap.sold_count, snap.listing_count) == (DAY2, 1234, 20)
        for sid in (8, 9):
            assert s.get(Shop, sid).name == f"Old{sid}"
            assert s.scalars(select(ShopSnapshot).where(ShopSnapshot.shop_id == sid)).all() == []
