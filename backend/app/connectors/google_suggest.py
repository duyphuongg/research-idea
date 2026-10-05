"""Google Autocomplete (US): niche ideas people type after '<seed> shirt'."""

import asyncio
from datetime import date
from typing import Any

import httpx

from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal, RawBatch
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.keywords import normalize_keyword

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
QUERY_SUFFIXES = ("shirt", "hoodie", "sweatshirt")
MAX_SUGGESTIONS = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)


class GoogleSuggestConnector:
    name = "google_suggest"
    kind = "trend"

    def __init__(self, *, min_interval: float = 1.0, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=15.0) as client:
            for keyword in keywords:
                for suffix in QUERY_SUFFIXES:
                    query = f"{keyword} {suffix}"
                    try:
                        payloads.append(
                            {"keyword": keyword, "query": query, "suggestions": await self._suggest(client, query)}
                        )
                    except ConnectorError as exc:
                        errors.append(f"{query}: {exc}")
        return RawBatch(source=self.name, payloads=payloads, errors=errors)

    async def _suggest(self, client: httpx.AsyncClient, query: str) -> list[str]:
        response = await request_with_retry(
            client,
            "GET",
            SUGGEST_URL,
            params={"client": "firefox", "hl": "en", "gl": "us", "q": query},
            limiter=self._limiter,
            sleep=self._sleep,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectorError("invalid JSON from suggest") from exc
        if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
            raise ConnectorError("unexpected suggest response shape")
        return [str(s) for s in data[1]]

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        best: dict[tuple[str, str], int] = {}
        for payload in raw.payloads:
            query = normalize_keyword(payload["query"])
            for rank, suggestion in enumerate(payload.get("suggestions", [])[:MAX_SUGGESTIONS], start=1):
                text = normalize_keyword(suggestion)
                if not text or text == query:
                    continue
                key = (payload["keyword"], text)
                best[key] = min(best.get(key, rank), rank)
        return NormalizedBatch(
            signals=[
                NormalizedSignal(
                    keyword=text, source=self.name, metric="suggest_score",
                    value=float(MAX_SUGGESTIONS + 1 - rank), date=today,
                    origin="discovered", parent=seed,
                )
                for (seed, text), rank in best.items()
            ]
        )
