import asyncio
import json
import random
from datetime import date
from pathlib import Path

from app.analysis.amazon import AmazonCategory, AmazonConfig
from app.connectors.amazon import AmazonConnector, PageResult
from app.connectors.base import RawBatch

ITEMS = json.loads((Path(__file__).parent / "fixtures" / "amazon" / "page_items.json").read_text())
TODAY = date(2026, 10, 7)
CAPTCHA = "Enter the characters you see below"


def cfg(lists=("bestsellers", "new_releases"), pages=2) -> AmazonConfig:
    return AmazonConfig(
        categories=(AmazonCategory("women_tshirts", "9056923011", "tshirt"),),
        licensed_terms=("superman",),
        lists=lists,
        pages=pages,
        min_phrase_products=3,
    )


class FakeLoader:
    def __init__(self, results):
        self.results = results  # callable(url) -> PageResult | Exception
        self.urls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __call__(self, url):
        self.urls.append(url)
        res = self.results(url)
        if isinstance(res, Exception):
            raise res
        return res


FULL = list(ITEMS) + [
    {"rank": f"#{i}", "href": f"/x/dp/B0FILL{i:05d}", "title": f"Filler {i}", "img": None}
    for i in range(len(ITEMS) + 1, 51)
]


def ok(_url=""):
    return PageResult(200, "Best Sellers", list(FULL))


def make(loader, config=None):
    sleeps: list[float] = []

    async def fake_sleep(s):
        sleeps.append(s)

    conn = AmazonConnector(config or cfg(), loader_factory=lambda: loader, sleep=fake_sleep, rng=random.Random(1))
    return conn, sleeps


def test_normalize_products_ranks_signals():
    conn, _ = make(FakeLoader(ok))
    raw = RawBatch("amazon", [{"category": "women_tshirts", "list": "bestsellers", "page": 1, "items": ITEMS}])
    batch = conn.normalize(raw, TODAY)
    assert len(batch.products) == 6  # duplicate ASIN collapsed
    by_title = {p.title: p for p in batch.products}
    sup = by_title["Popfunk Superman Classic Logo T-Shirt"]
    assert sup.licensed is True and by_title["Retro Superb Mom Shirt"].licensed is False
    assert sup.external_id.startswith("B0") and len(sup.external_id) == 10
    assert sup.url == f"https://www.amazon.com/dp/{sup.external_id}"
    assert sup.source == "amazon" and sup.price is None and sup.currency is None
    assert sup.product_type == "tshirt" and sup.rank == 4 and sup.bsr == 4
    first = batch.products[0]
    assert first.reviews == 2959 and first.rating == 4.6
    assert by_title["Pickleball Dad Funny Pickleball T-Shirt"].reviews == 1200
    assert len(batch.ranks) == 6
    assert {(r.category_key, r.list_name, r.date) for r in batch.ranks} == {("women_tshirts", "bestsellers", TODAY)}
    phrases = {s.keyword: s.value for s in batch.signals}
    assert phrases.get("funny pickleball") == 3
    assert not any("superman" in k for k in phrases)
    s = batch.signals[0]
    assert (s.source, s.metric, s.date, s.origin) == ("amazon", "title_phrase_count", TODAY, "discovered")


def test_normalize_bsr_only_for_bestsellers_and_best_rank_kept():
    conn, _ = make(FakeLoader(ok))
    raw = RawBatch("amazon", [
        {"category": "women_tshirts", "list": "new_releases", "page": 1, "items": ITEMS[:2]},
        {"category": "women_tshirts", "list": "bestsellers", "page": 2, "items": [dict(ITEMS[0], rank="#51")]},
    ])
    batch = conn.normalize(raw, TODAY)
    p = next(p for p in batch.products if p.external_id == "B01ABCDEF1")
    assert p.rank == 51 and p.bsr == 51  # bestsellers entry preferred
    q = next(p for p in batch.products if p.title.startswith("Pickleball Dad"))
    assert q.rank == 2 and q.bsr is None  # only on new releases
    assert len(batch.ranks) == 3


def test_fetch_happy_path_with_delays():
    loader = FakeLoader(ok)
    conn, sleeps = make(loader)
    raw = asyncio.run(conn.fetch(["ignored"]))
    assert raw.errors == [] and len(raw.payloads) == 4
    assert loader.urls[0] == "https://www.amazon.com/gp/bestsellers/fashion/9056923011?pg=1"
    assert "new-releases" in loader.urls[2]
    assert raw.payloads[1] == {"category": "women_tshirts", "list": "bestsellers", "page": 2, "items": FULL}
    assert len(sleeps) == 3 and all(4 <= s <= 8 for s in sleeps)


def test_fetch_blocked_page_recorded():
    def results(url):
        return PageResult(200, CAPTCHA, []) if "pg=2" in url and "bestsellers" in url else ok()

    conn, _ = make(FakeLoader(results))
    raw = asyncio.run(conn.fetch([]))
    assert raw.errors == ["women_tshirts/bestsellers/p2: blocked"]
    assert len(raw.payloads) == 3


def test_fetch_two_consecutive_blocks_abort():
    loader = FakeLoader(lambda url: PageResult(503, "", []) if "pg=1" in url else ok())
    conn, _ = make(loader, cfg(pages=3))
    loader.results = lambda url: RuntimeError("nav timeout")
    raw = asyncio.run(conn.fetch([]))
    assert raw.errors == [
        "women_tshirts/bestsellers/p1: blocked",
        "women_tshirts/bestsellers/p2: blocked",
        "aborted: Amazon is blocking requests",
    ]
    assert len(loader.urls) == 2 and raw.payloads == []


def test_enabled_reflects_playwright(monkeypatch):
    import importlib.util

    conn, _ = make(FakeLoader(ok))
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    assert conn.enabled() is False
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    assert conn.enabled() is True


def test_normalize_excludes_non_pod_titles_from_phrases_but_keeps_products():
    conn, _ = make(FakeLoader(ok), cfg())
    conn._config = AmazonConfig(
        categories=cfg().categories, non_pod_terms=("modify by amazon",), min_phrase_products=3
    )
    items = [
        {"rank": f"#{i}", "href": f"/dp/B0AAAAAA0{i}", "title": "Modify by Amazon Custom Spooky Season Ghost", "img": None}
        for i in range(1, 4)
    ]
    raw = RawBatch("amazon", [{"category": "women_tshirts", "list": "bestsellers", "page": 1, "items": items}], [])
    batch = conn.normalize(raw, TODAY)
    assert len(batch.products) == 3
    assert batch.signals == []


def test_normalize_falls_back_to_link_text_and_position():
    conn, _ = make(FakeLoader(ok), cfg())
    items = [
        {"rank": "#1", "href": "/dp/B0AAAAAA01", "title": "First", "img": None},
        {"rank": None, "href": "/dp/B0AAAAAA02", "title": None, "text": "  Linked title  ", "img": None},
    ]
    raw = RawBatch("amazon", [{"category": "women_tshirts", "list": "bestsellers", "page": 2, "items": items}], [])
    batch = conn.normalize(raw, TODAY)
    by_id = {p.external_id: p for p in batch.products}
    assert by_id["B0AAAAAA02"].title == "Linked title"
    assert by_id["B0AAAAAA02"].rank == 52  # page 2, 2nd position


# ---- final-review fixes ----

import sys
import types

import pytest

from app.connectors.amazon import PlaywrightLoader
from app.connectors.base import ConnectorError


class FakeCtx:
    def __init__(self, log, fail_close=False):
        self.log, self.fail_close = log, fail_close
        self.kwargs = None

    async def close(self):
        self.log.append("context")
        if self.fail_close:
            raise RuntimeError("ctx close")


class FakeBrowser:
    def __init__(self, log, new_context_error=None, fail_close=False):
        self.log, self.err, self.fail_close = log, new_context_error, fail_close
        self.ctx = FakeCtx(log)
        self.ctx_kwargs = None

    async def new_context(self, **kwargs):
        self.ctx_kwargs = kwargs
        if self.err:
            raise self.err
        return self.ctx

    async def close(self):
        self.log.append("browser")
        if self.fail_close:
            raise RuntimeError("browser close")


class FakePW:
    def __init__(self, log, launch_error=None, browser=None):
        self.log = log
        self.launch_error = launch_error
        self.browser = browser or FakeBrowser(log)
        self.chromium = self

    async def launch(self, **kwargs):
        if self.launch_error:
            raise self.launch_error
        return self.browser

    async def stop(self):
        self.log.append("pw")


def patch_playwright(monkeypatch, pw):
    class Starter:
        async def start(self):
            return pw

    mod = types.ModuleType("playwright.async_api")
    mod.async_playwright = lambda: Starter()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)


async def test_loader_exit_closes_everything_even_if_one_fails(monkeypatch):
    log: list[str] = []
    browser = FakeBrowser(log)
    browser.ctx.fail_close = True
    patch_playwright(monkeypatch, FakePW(log, browser=browser))
    loader = PlaywrightLoader()
    await loader.__aenter__()
    with pytest.raises(RuntimeError, match="ctx close"):
        await loader.__aexit__(None, None, None)
    assert log == ["context", "browser", "pw"]


async def test_loader_enter_failure_cleans_up_and_reraises(monkeypatch):
    log: list[str] = []
    browser = FakeBrowser(log, new_context_error=ValueError("ctx boom"))
    patch_playwright(monkeypatch, FakePW(log, browser=browser))
    with pytest.raises(ValueError, match="ctx boom"):
        await PlaywrightLoader().__aenter__()
    assert log == ["browser", "pw"]


async def test_loader_missing_chromium_message(monkeypatch):
    log: list[str] = []
    err = Exception("BrowserType.launch: Executable doesn't exist at /x/chrome")
    patch_playwright(monkeypatch, FakePW(log, launch_error=err))
    with pytest.raises(ConnectorError, match="make install"):
        await PlaywrightLoader().__aenter__()
    assert log == ["pw"]


async def test_loader_context_has_no_user_agent_override(monkeypatch):
    log: list[str] = []
    pw = FakePW(log)
    patch_playwright(monkeypatch, pw)
    loader = PlaywrightLoader()
    await loader.__aenter__()
    assert "user_agent" not in pw.browser.ctx_kwargs
    assert pw.browser.ctx_kwargs["locale"] == "en-US"
    await loader.__aexit__(None, None, None)


async def test_fetch_time_budget_exceeded():
    now = [0.0]

    async def sleep(s):
        now[0] += 600  # each pause "takes" 10 minutes

    loader = FakeLoader(ok)
    conn = AmazonConnector(
        cfg(), loader_factory=lambda: loader, sleep=sleep, rng=random.Random(1),
        clock=lambda: now[0],
    )
    raw = await conn.fetch([])
    assert raw.errors == ["aborted: time budget exceeded"]
    assert len(raw.payloads) == 2  # p1, p2 fetched; budget (900s) exceeded before p3


def short_page(n):
    return PageResult(200, "Best Sellers", [dict(ITEMS[0], href=f"/dp/B0SHORT{i:03d}", rank=f"#{i+1}") for i in range(n)])


async def test_short_page_is_nonfatal_error_not_blocked():
    def results(url):
        return short_page(30) if "bestsellers" in url and "pg=1" in url else ok()

    conn, _ = make(FakeLoader(results))
    raw = await conn.fetch([])
    assert raw.errors == ["women_tshirts/bestsellers/p1: only 30 items"]
    assert len(raw.payloads) == 4  # short page still kept


async def test_short_pages_do_not_trigger_blocked_abort():
    conn, _ = make(FakeLoader(lambda url: short_page(10)), cfg(pages=3))
    raw = await conn.fetch([])
    assert not any("aborted" in e for e in raw.errors)
    assert len(raw.payloads) == 6


def test_normalize_duplicate_asin_across_pages_keeps_min_rank():
    conn, _ = make(FakeLoader(ok))
    raw = RawBatch("amazon", [
        {"category": "women_tshirts", "list": "bestsellers", "page": 1, "items": [dict(ITEMS[0], rank="#50")]},
        {"category": "women_tshirts", "list": "bestsellers", "page": 2, "items": [dict(ITEMS[0], rank="#51")]},
    ])
    batch = conn.normalize(raw, TODAY)
    assert [(r.external_id, r.rank) for r in batch.ranks] == [("B01ABCDEF1", 50)]


def test_amazon_replaces_daily_signals():
    assert AmazonConnector.replace_daily_signals is True
