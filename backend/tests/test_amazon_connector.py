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


def ok(_url=""):
    return PageResult(200, "Best Sellers", list(ITEMS))


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
    assert raw.payloads[1] == {"category": "women_tshirts", "list": "bestsellers", "page": 2, "items": ITEMS}
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
