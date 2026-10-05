"""Etsy Open API v3: top apparel listings for each seed keyword."""

import asyncio
import html
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.analysis.product_type import classify_product_type
from app.connectors.base import (
    ConnectorError,
    NormalizedBatch,
    NormalizedProduct,
    NormalizedSignal,
    RawBatch,
)
from app.connectors.http import RateLimiter, Sleep, request_with_retry

BASE_URL = "https://openapi.etsy.com/v3/application"
# product_type -> suffix appended to the seed keyword for the search query
QUERY_SUFFIXES = {"tshirt": "shirt", "sweatshirt": "sweatshirt", "hoodie": "hoodie"}
SEARCH_LIMIT = 50


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
        search = (
            await self._get(
                client,
                "/listings/active",
                {"keywords": query, "limit": SEARCH_LIMIT, "sort_on": "score"},
            )
        ).json()
        ids = [str(item["listing_id"]) for item in search.get("results", [])]
        details: dict[str, Any] = {"results": []}
        if ids:
            details = (
                await self._get(
                    client,
                    "/listings/batch",
                    {"listing_ids": ",".join(ids), "includes": "Images,Shop"},
                )
            ).json()
        return {
            "keyword": keyword,
            "query": query,
            "product_type": product_type,
            "search": search,
            "details": details,
        }

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> httpx.Response:
        return await request_with_retry(
            client, "GET", path, params=params, limiter=self._limiter, sleep=self._sleep
        )

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
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
                str(d["listing_id"]): d for d in payload.get("details", {}).get("results", [])
            }
            for rank, item in enumerate(search.get("results", []), start=1):
                listing = {**item, **details.get(str(item["listing_id"]), {})}
                product = _to_product(listing, keyword, rank)
                if product is not None:
                    batch.products.append(product)
        return batch


def _to_product(listing: dict[str, Any], keyword: str, rank: int) -> NormalizedProduct | None:
    title = html.unescape(listing.get("title") or "").strip()
    product_type = classify_product_type(title)
    if product_type == "other":
        return None
    price = listing.get("price") or {}
    amount = price.get("amount")
    divisor = price.get("divisor") or 1
    images = listing.get("images") or []
    shop = listing.get("shop") or {}
    created = listing.get("original_creation_timestamp") or listing.get("creation_timestamp")
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
        listed_at=(
            datetime.fromtimestamp(created, tz=timezone.utc).replace(tzinfo=None)
            if created
            else None
        ),
        keyword=keyword,
        rank=rank,
        favorites=listing.get("num_favorers"),
    )
