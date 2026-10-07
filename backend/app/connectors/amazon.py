"""Amazon Best Sellers / New Releases connector (headless Chromium, US, no prices)."""

import asyncio
import importlib.util
import logging
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.analysis.amazon import (
    AmazonConfig,
    is_licensed,
    list_url,
    load_amazon_config,
    parse_rating,
    parse_reviews,
    title_phrases,
)
from app.connectors.base import (
    NormalizedBatch,
    NormalizedProduct,
    NormalizedRank,
    NormalizedSignal,
    RawBatch,
)

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BLOCK_MARKERS = ("captcha", "enter the characters you see", "sorry! something went wrong")
_ASIN_RE = re.compile(r"/dp/(B0[A-Z0-9]{8})")
_RANK_RE = re.compile(r"#\s*(\d+)")

_EXTRACT_JS = """els => els.map(e => {
  const a = e.querySelector('a[href*="/dp/"]');
  const img = e.querySelector('img');
  const rank = e.querySelector('.zg-bdg-text');
  const rating = e.querySelector('i[class*="a-icon-star"] span, .a-icon-alt');
  const reviews = e.querySelector('a[href*="product-reviews"] span');
  return {rank: rank && rank.innerText, href: a && a.getAttribute('href'),
          title: img && img.getAttribute('alt'), img: img && img.getAttribute('src'),
          rating: rating && rating.innerText, reviews: reviews && reviews.innerText};
})"""


@dataclass
class PageResult:
    status: int
    text_sample: str
    items: list[dict[str, Any]]


PageLoader = Callable[[str], Awaitable[PageResult]]


class PlaywrightLoader:
    """Async context manager: one headless Chromium reused for all pages."""

    async def __aenter__(self) -> "PlaywrightLoader":
        from playwright.async_api import async_playwright  # lazy: optional dependency

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            locale="en-US", user_agent=USER_AGENT, viewport={"width": 1400, "height": 2400}
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._context.close()
        await self._browser.close()
        await self._pw.stop()

    async def __call__(self, url: str) -> PageResult:
        page = await self._context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            for _ in range(6):
                await page.mouse.wheel(0, 3000)
                await page.wait_for_timeout(700)
            items = await page.eval_on_selector_all("div[id^='p13n-asin-index']", _EXTRACT_JS)
            if not items:
                items = await page.eval_on_selector_all("div[data-asin]", _EXTRACT_JS)
            text = (await page.inner_text("body"))[:2000]
            return PageResult(response.status if response else 0, text, items)
        finally:
            await page.close()


def _is_blocked(result: PageResult) -> bool:
    low = (result.text_sample or "").lower()
    return result.status >= 400 or any(m in low for m in BLOCK_MARKERS) or not result.items


class AmazonConnector:
    name = "amazon"
    kind = "product"

    def __init__(
        self,
        config: AmazonConfig | None = None,
        *,
        loader_factory: Callable[[], Any] = PlaywrightLoader,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._loader_factory = loader_factory
        self._sleep = sleep
        self._rng = rng or random.Random()

    @property
    def config(self) -> AmazonConfig:
        if self._config is None:
            self._config = load_amazon_config()
        return self._config

    def enabled(self) -> bool:
        return importlib.util.find_spec("playwright") is not None

    async def fetch(self, keywords: list[str]) -> RawBatch:
        """Seed keywords are ignored: Best Sellers lists are category-wide."""
        cfg = self.config
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []
        consecutive = 0
        first = True
        async with self._loader_factory() as load:
            for category in cfg.categories:
                for list_name in cfg.lists:
                    for page in range(1, cfg.pages + 1):
                        if not first:
                            await self._sleep(self._rng.uniform(*cfg.delay_seconds))
                        first = False
                        label = f"{category.key}/{list_name}/p{page}"
                        try:
                            result = await load(list_url(list_name, category.node, page))
                        except Exception as exc:  # noqa: BLE001 - any loader failure == blocked
                            logger.warning("Amazon %s failed: %s", label, exc)
                            result = None
                        if result is None or _is_blocked(result):
                            errors.append(f"{label}: blocked")
                            consecutive += 1
                            if consecutive >= 2:
                                errors.append("aborted: Amazon is blocking requests")
                                return RawBatch(self.name, payloads, errors)
                            continue
                        consecutive = 0
                        payloads.append(
                            {"category": category.key, "list": list_name, "page": page,
                             "items": result.items}
                        )
        return RawBatch(self.name, payloads, errors)

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        cfg = self.config
        categories = {c.key: c for c in cfg.categories}
        best: dict[str, tuple[tuple[int, int], NormalizedProduct]] = {}
        ranks: list[NormalizedRank] = []
        for payload in raw.payloads:
            category = categories.get(payload.get("category"))
            if category is None:
                continue
            list_name = payload.get("list", "")
            seen: set[str] = set()
            for item in payload.get("items", []):
                m = _ASIN_RE.search(item.get("href") or "")
                rm = _RANK_RE.search(item.get("rank") or "")
                title = (item.get("title") or "").strip()
                if not m or not rm or not title or m.group(1) in seen:
                    continue
                asin, rank = m.group(1), int(rm.group(1))
                seen.add(asin)
                ranks.append(NormalizedRank(asin, category.key, list_name, rank, today))
                product = NormalizedProduct(
                    source="amazon",
                    external_id=asin,
                    title=title,
                    url=f"https://www.amazon.com/dp/{asin}",
                    image_url=item.get("img"),
                    shop_name=None,
                    price=None,
                    currency=None,
                    product_type=category.product_type,
                    listed_at=None,
                    keyword=None,
                    rank=rank,
                    reviews=parse_reviews(item.get("reviews")),
                    rating=parse_rating(item.get("rating")),
                    bsr=rank if list_name == "bestsellers" else None,
                    licensed=is_licensed(title, cfg.licensed_terms),
                )
                key = (0 if list_name == "bestsellers" else 1, rank)
                if asin not in best or key < best[asin][0]:
                    best[asin] = (key, product)

        products = [p for _, p in best.values()]
        titles = [p.title for p in products if not p.licensed]
        signals = [
            NormalizedSignal(
                keyword=phrase, source="amazon", metric="title_phrase_count",
                value=count, date=today, origin="discovered",
            )
            for phrase, count in title_phrases(titles, cfg.min_phrase_products, cfg.max_phrases)
        ]
        return NormalizedBatch(products=products, signals=signals, ranks=ranks)
