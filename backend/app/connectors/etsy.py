"""Etsy Open API v3: top apparel listings for each seed keyword."""

import asyncio
import html
from collections import Counter
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.analysis.product_type import classify_product_type, is_digital_listing
from app.connectors.base import (
    ConnectorError,
    NormalizedBatch,
    NormalizedProduct,
    NormalizedSignal,
    RawBatch,
)
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.keywords import normalize_keyword

BASE_URL = "https://openapi.etsy.com/v3/application"
# product_type -> suffix appended to the seed keyword for the search query
QUERY_SUFFIXES = {"tshirt": "shirt", "sweatshirt": "sweatshirt", "hoodie": "hoodie"}
SEARCH_LIMIT = 100
MIN_TAG_COUNT = 3  # a tag must appear on >= 3 US listings of the seed to become a niche
MAX_TAGS_PER_SEED = 30
NEW_LISTING_DAYS = 30


class EtsyConnector:
    name = "etsy"
    kind = "product"

    def __init__(
        self, api_key: str | None, *, min_interval: float = 0.2, sleep: Sleep = asyncio.sleep
    ) -> None:
        self.api_key = api_key
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)

    def enabled(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, keywords: list[str]) -> RawBatch:
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(
            base_url=BASE_URL, headers={"x-api-key": self.api_key or ""}, timeout=30.0
        ) as client:
            for keyword in keywords:
                for product_type, suffix in QUERY_SUFFIXES.items():
                    query = f"{keyword} {suffix}"
                    try:
                        payloads.append(
                            await self._fetch_query(client, keyword, query, product_type)
                        )
                    except ConnectorError as exc:
                        errors.append(f"{query}: {exc}")
        return RawBatch(source=self.name, payloads=payloads, errors=errors)

    async def _fetch_query(
        self, client: httpx.AsyncClient, keyword: str, query: str, product_type: str
    ) -> dict[str, Any]:
        search = await self._get_json(
            client,
            "/listings/active",
            {"keywords": query, "limit": SEARCH_LIMIT, "sort_on": "score"},
        )
        ids = [str(i["listing_id"]) for i in search.get("results", []) if "listing_id" in i]
        details: dict[str, Any] = {"results": []}
        if ids:
            details = await self._get_json(
                client,
                "/listings/batch",
                {"listing_ids": ",".join(ids), "includes": "Images,Shop"},
            )
        return {
            "keyword": keyword,
            "query": query,
            "product_type": product_type,
            "search": search,
            "details": details,
        }

    async def _get_json(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self._get(client, path, params)
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(f"invalid JSON from {path}") from exc

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> httpx.Response:
        return await request_with_retry(
            client, "GET", path, params=params, limiter=self._limiter, sleep=self._sleep
        )

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
        kept: dict[str, dict[str, dict[str, Any]]] = {}  # seed -> listing_id -> listing
        for payload in raw.payloads:
            keyword = payload["keyword"]
            search = payload.get("search", {})
            if search.get("count") is not None:
                batch.signals.append(
                    NormalizedSignal(
                        keyword=keyword,
                        source=self.name,
                        metric=f"listing_count_{payload['product_type']}",
                        value=float(search["count"]),
                        date=today,
                    )
                )
            details = {
                str(d["listing_id"]): d
                for d in payload.get("details", {}).get("results", [])
                if "listing_id" in d
            }
            for rank, item in enumerate(search.get("results", []), start=1):
                if "listing_id" not in item:
                    continue
                listing = {**item, **details.get(str(item["listing_id"]), {})}
                product = _to_product(listing, keyword, rank)
                if product is not None:
                    batch.products.append(product)
                    kept.setdefault(keyword, {}).setdefault(product.external_id, listing)
        for keyword, listings in kept.items():
            batch.signals.extend(_keyword_signals(keyword, list(listings.values()), today))
        return batch


def _created_at(listing: dict[str, Any]) -> datetime | None:
    created = listing.get("original_creation_timestamp") or listing.get("creation_timestamp")
    return datetime.fromtimestamp(created, tz=timezone.utc).replace(tzinfo=None) if created else None


def _is_us_usd(listing: dict[str, Any]) -> bool:
    shop = listing.get("shop") or {}
    price = listing.get("price") or {}
    return shop.get("is_shop_us_based") is True and price.get("currency_code") == "USD"


def _to_product(listing: dict[str, Any], keyword: str | None, rank: int) -> NormalizedProduct | None:
    title = html.unescape(listing.get("title") or "").strip()
    product_type = classify_product_type(title)
    if product_type == "other" or not _is_us_usd(listing):
        return None
    if is_digital_listing(title, listing.get("listing_type")):
        return None
    price = listing.get("price") or {}
    amount = price.get("amount")
    divisor = price.get("divisor") or 1
    images = listing.get("images") or []
    shop = listing.get("shop") or {}
    listing_id = str(listing["listing_id"])
    return NormalizedProduct(
        source="etsy",
        external_id=listing_id,
        title=title,
        url=listing.get("url") or f"https://www.etsy.com/listing/{listing_id}",
        image_url=images[0].get("url_570xN") if images else None,
        shop_name=shop.get("shop_name"),
        price=amount / divisor if amount is not None else None,
        currency=price.get("currency_code"),
        product_type=product_type,
        listed_at=_created_at(listing),
        keyword=keyword,
        rank=rank,
        favorites=listing.get("num_favorers"),
        views=listing.get("views"),
        shop_sold_count=shop.get("transaction_sold_count"),
        tags=_tags(listing),
    )


def _tags(listing: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for raw_tag in listing.get("tags") or []:
        tag = normalize_keyword(html.unescape(str(raw_tag)))
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def _keyword_signals(
    keyword: str, listings: list[dict[str, Any]], today: date
) -> list[NormalizedSignal]:
    def signal(metric: str, value: float) -> NormalizedSignal:
        return NormalizedSignal(keyword=keyword, source="etsy", metric=metric, value=value, date=today)

    rates: list[float] = []
    new_listings = 0
    for listing in listings:
        created = _created_at(listing)
        if created is None:
            continue
        age_days = max(1, (today - created.date()).days)
        if listing.get("views") is not None:
            rates.append(listing["views"] / age_days)
        if age_days <= NEW_LISTING_DAYS:
            new_listings += 1

    signals = [
        signal("us_listing_count", float(len(listings))),
        signal("new_listings_30d", float(new_listings)),
    ]
    if rates:
        signals.append(signal("views_per_day", sum(rates) / len(rates)))

    seed = normalize_keyword(keyword)
    tag_counts = Counter(
        tag
        for listing in listings
        for tag in {normalize_keyword(html.unescape(t)) for t in listing.get("tags") or []}
        if tag and tag != seed
    )
    for tag, count in tag_counts.most_common(MAX_TAGS_PER_SEED):
        if count < MIN_TAG_COUNT:
            break
        signals.append(
            NormalizedSignal(
                keyword=tag, source="etsy_tags", metric="tag_count", value=float(count),
                date=today, origin="discovered", parent=keyword,
            )
        )
    return signals
