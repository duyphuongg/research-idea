"""Etsy Listing Signals job: discover new US apparel listings, track them daily, classify."""

import asyncio
import logging
from collections import Counter
from collections.abc import AsyncIterator, Callable
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.listing_signals import (
    BREAKOUT_STATUSES,
    SignalsConfig,
    classify,
    compute_metrics,
    load_signals_config,
)
from app.analysis.velocity import SnapshotPoint
from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal
from app.connectors.etsy import BASE_URL, _created_at, _to_product
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.keywords import normalize_keyword
from app.models import ListingSignal, Product, ProductSnapshot
from app.pipeline.scan import MAX_ERROR_LEN, finish_run, start_run
from app.pipeline.store import persist_batch, upsert_product

logger = logging.getLogger(__name__)
SOURCE = "etsy_signals"
PAGE_SIZE = 100
BATCH_SIZE = 100


class EtsySignalsClient:
    def __init__(self, api_key: str, *, min_interval: float = 0.2, sleep: Sleep = asyncio.sleep):
        self.api_key = api_key
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)
        self._client: httpx.AsyncClient | None = None
        self.failed_ids: set[str] = set()

    async def __aenter__(self) -> "EtsySignalsClient":
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, headers={"x-api-key": self.api_key}, timeout=30.0
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await request_with_retry(
            self._client, "GET", path, params=params, limiter=self._limiter, sleep=self._sleep
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ConnectorError(f"invalid JSON from {path}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("results", []), list):
            raise ConnectorError(f"unexpected response shape from {path}")
        return data

    async def search_new(self, query: str, pages: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(pages):
            data = await self._get_json(
                "/listings/active",
                {"keywords": query, "sort_on": "created", "sort_order": "desc",
                 "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
            )
            batch = data.get("results", [])
            results.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
        return results

    async def _fetch_chunk(self, chunk: list[str]) -> list[dict[str, Any]]:
        data = await self._get_json(
            "/listings/batch", {"listing_ids": ",".join(chunk), "includes": "Images,Shop"}
        )
        return data.get("results", [])

    async def _fetch_bisecting(
        self, chunk: list[str]
    ) -> AsyncIterator[tuple[list[dict[str, Any]], str | None]]:
        try:
            details = await self._fetch_chunk(chunk)
        except ConnectorError as exc:
            if len(chunk) == 1:
                self.failed_ids.update(chunk)
                yield [], f"listing {chunk[0]}: {exc}"
                return
            mid = len(chunk) // 2
            for half in (chunk[:mid], chunk[mid:]):
                async for result in self._fetch_bisecting(half):
                    yield result
            return
        yield details, None

    async def iter_batches(
        self, ids: list[str]
    ) -> AsyncIterator[tuple[list[dict[str, Any]], str | None]]:
        """Yield (details, error) per fetched piece; failing chunks are bisected down to single ids."""
        for start in range(0, len(ids), BATCH_SIZE):
            async for result in self._fetch_bisecting(ids[start : start + BATCH_SIZE]):
                yield result


def trim_images(listing: dict[str, Any]) -> dict[str, Any]:
    """Keep only the first image (all _to_product needs) to bound memory."""
    images = listing.get("images")
    if isinstance(images, list):
        listing["images"] = images[:1]
    return listing


def tracked_listing_ids(session: Session, today: date, config: SignalsConfig) -> set[str]:
    cutoff = today - timedelta(days=config.track_days)
    cutoff_dt = datetime.combine(cutoff, time.min)
    rows = session.scalars(
        select(Product.external_id)
        .join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(
            Product.source == "etsy",
            ListingSignal.status != "gone",
            or_(
                Product.listed_at >= cutoff_dt,
                (Product.listed_at.is_(None)) & (ListingSignal.discovered_on >= cutoff),
            ),
        )
    )
    return set(rows)


def gone_listing_ids(session: Session) -> set[str]:
    return set(
        session.scalars(
            select(Product.external_id)
            .join(ListingSignal, ListingSignal.product_id == Product.id)
            .where(Product.source == "etsy", ListingSignal.status == "gone")
        )
    )


async def collect_listings(
    client: EtsySignalsClient,
    config: SignalsConfig,
    seeds: list[str],
    tracked: set[str],
    today: date,
    skip: set[str] | frozenset[str] = frozenset(),
) -> tuple[list[str], dict[str, str], list[str]]:
    errors: list[str] = []
    queries = list(config.queries) + [f"{seed} {config.seed_query_suffix}" for seed in seeds]
    oldest = datetime.combine(today - timedelta(days=config.max_age_days), time.min)
    discovery: dict[str, str] = {}
    for query in dict.fromkeys(queries):
        try:
            found = await client.search_new(query, config.pages_per_query)
        except ConnectorError as exc:
            errors.append(f"{query}: {exc}")
            continue
        for item in found:
            if item.get("listing_id") is None:
                continue
            lid = str(item["listing_id"])
            if lid in tracked or lid in discovery or lid in skip:
                continue
            created = _created_at(item)
            if created is None or created < oldest:
                continue
            discovery[lid] = query
    capacity = max(0, config.max_tracked - len(tracked))
    discovery = dict(list(discovery.items())[:capacity])
    ids = sorted(tracked) + list(discovery)
    return ids, discovery, errors


def persist_listings(
    session: Session,
    details: list[dict[str, Any]],
    discovery: dict[str, str],
    today: date,
    config: SignalsConfig,
    tracked: set[str] | frozenset[str] = frozenset(),
) -> tuple[int, int, int]:
    discovered = refreshed = gone = 0
    for listing in details:
        if listing.get("listing_id") is None:
            continue
        item = _to_product(listing, None, 0)
        if item is None:
            if str(listing["listing_id"]) in tracked:
                gone += mark_gone(session, {str(listing["listing_id"])}, today)
            continue
        product = upsert_product(session, item, today)
        signal = session.get(ListingSignal, product.id)
        is_new = signal is None
        if is_new:
            if item.external_id not in discovery:
                continue  # untracked and not newly discovered
            signal = ListingSignal(
                product_id=product.id,
                discovered_on=today,
                discovery_query=discovery[item.external_id][:200],
            )
            session.add(signal)
        points = [
            SnapshotPoint(s.date, s.reviews, s.favorites, s.views)
            for s in session.scalars(
                select(ProductSnapshot).where(ProductSnapshot.product_id == product.id)
            )
        ]
        metrics = compute_metrics(
            points,
            product.listed_at.date() if product.listed_at else None,
            today,
            min_dsr_views=config.thresholds.dsr_min_delta_views,
        )
        signal.status = classify(metrics, config.thresholds)
        signal.age_days = metrics.age_days
        signal.views = metrics.views
        signal.saves = metrics.saves
        signal.delta_views = metrics.delta_views
        signal.delta_saves = metrics.delta_saves
        signal.dsr = metrics.dsr
        signal.updated_on = today
        if is_new:
            discovered += 1
        else:
            refreshed += 1
    session.flush()
    return discovered, refreshed, gone


def mark_gone(session: Session, external_ids: set[str], today: date) -> int:
    if not external_ids:
        return 0
    signals = session.scalars(
        select(ListingSignal)
        .join(Product, ListingSignal.product_id == Product.id)
        .where(Product.source == "etsy", Product.external_id.in_(external_ids))
    ).all()
    for signal in signals:
        signal.status = "gone"
        signal.updated_on = today
    session.flush()
    return len(signals)


def tag_signals(session: Session, config: SignalsConfig, today: date) -> NormalizedBatch:
    """Tags carried by today's breakout listings (counted once per listing) -> trend signals."""
    rows = session.scalars(
        select(Product.tags)
        .join(ListingSignal, ListingSignal.product_id == Product.id)
        .where(ListingSignal.status.in_(BREAKOUT_STATUSES), ListingSignal.updated_on == today)
    )
    counts: Counter[str] = Counter()
    for tags in rows:
        counts.update({normalize_keyword(t) for t in (tags or []) if normalize_keyword(t)})
    ranked = sorted(
        ((tag, n) for tag, n in counts.items() if n >= config.min_tag_listings),
        key=lambda kv: (-kv[1], kv[0]),
    )[: config.max_tags]
    return NormalizedBatch(
        signals=[
            NormalizedSignal(
                keyword=tag,
                source=SOURCE,
                metric="breakout_tag_count",
                value=float(n),
                date=today,
                origin="discovered",
            )
            for tag, n in ranked
        ]
    )


async def run_listing_signals(
    session_factory: sessionmaker[Session],
    api_key: str,
    keywords: list[str],
    today: date,
    *,
    config: SignalsConfig | None = None,
    client_factory: Callable[[str], EtsySignalsClient] = EtsySignalsClient,
) -> int:
    config = config or load_signals_config()
    run_id = start_run(session_factory, SOURCE)
    status, records, error = "ok", 0, None
    try:
        with session_factory() as session:
            tracked = tracked_listing_ids(session, today, config)
            skip = gone_listing_ids(session)
        records = gone_total = 0
        got_details = False
        seen: set[str] = set()
        async with client_factory(api_key) as client:
            ids, discovery, errors = await collect_listings(
                client, config, keywords, tracked, today, skip
            )
            async for details, chunk_error in client.iter_batches(ids):
                if chunk_error:
                    errors.append(chunk_error)
                if not details:
                    continue
                got_details = True
                for listing in details:
                    trim_images(listing)
                    if listing.get("listing_id") is not None:
                        seen.add(str(listing["listing_id"]))
                with session_factory() as session:
                    discovered, refreshed, chunk_gone = persist_listings(
                        session, details, discovery, today, config, tracked
                    )
                    session.commit()
                records += discovered + refreshed
                gone_total += chunk_gone
                del details
            failed_ids = set(client.failed_ids)
        missing = tracked - seen - failed_ids
        with session_factory() as session:
            gone_total += mark_gone(session, missing, today)
            batch = tag_signals(session, config, today)
            persist_batch(session, batch, today)
            session.commit()
        records += len(batch.signals)
        logger.info("Listing signals: %d tracked listings marked gone", gone_total)
        if errors:
            status = "partial" if got_details else "failed"
            error = "\n".join(errors)[:MAX_ERROR_LEN]
    except Exception as exc:
        logger.exception("Listing signals job failed")
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LEN]
    finish_run(session_factory, run_id, SOURCE, status, records, error)
    return run_id
