"""Google Daily Search Trends RSS for the US (hot events / searches)."""

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date

import httpx

from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal, RawBatch
from app.connectors.google_suggest import USER_AGENT
from app.connectors.http import Sleep, request_with_retry

logger = logging.getLogger(__name__)
RSS_URL = "https://trends.google.com/trending/rss"
HT_NS = "{https://trends.google.com/trending/rss}"
_MULTIPLIERS = {"K": 1_000.0, "M": 1_000_000.0}


def parse_traffic(text: str) -> float | None:
    cleaned = text.strip().rstrip("+").replace(",", "").upper()
    if not cleaned:
        return None
    multiplier = _MULTIPLIERS.get(cleaned[-1], 1.0)
    number = cleaned[:-1] if cleaned[-1] in _MULTIPLIERS else cleaned
    try:
        return float(number) * multiplier
    except ValueError:
        return None


class GoogleDailyTrendsConnector:
    name = "google_daily"
    kind = "trend"

    def __init__(self, *, sleep: Sleep = asyncio.sleep) -> None:
        self._sleep = sleep

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        """Seed keywords are not used: the daily feed is country-wide."""
        async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20.0) as client:
            try:
                response = await request_with_retry(
                    client, "GET", RSS_URL, params={"geo": "US"}, sleep=self._sleep
                )
            except ConnectorError as exc:
                return RawBatch(source=self.name, payloads=[], errors=[str(exc)])
        return RawBatch(source=self.name, payloads=[{"geo": "US", "xml": response.text}])

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
        for payload in raw.payloads:
            try:
                root = ET.fromstring(payload["xml"])
            except ET.ParseError:
                logger.warning("Skipping malformed Daily Trends RSS payload")
                continue
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                traffic = parse_traffic(item.findtext(f"{HT_NS}approx_traffic") or "")
                if not title or traffic is None:
                    continue
                batch.signals.append(
                    NormalizedSignal(
                        keyword=title, source=self.name, metric="traffic", value=traffic,
                        date=today, origin="discovered",
                    )
                )
        return batch
