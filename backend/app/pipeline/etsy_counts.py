"""Etsy competition counts for the best-scored niches that only came from tags/suggest.

Seeds already get "<kw> shirt|sweatshirt|hoodie" result counts from the Etsy connector; this job
fills the same signals for the top child niches (one limit=1 search per type, ~90 calls a scan).
"""

import asyncio
import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import ConnectorError
from app.connectors.etsy import BASE_URL, QUERY_SUFFIXES
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.models import Keyword, KeywordScore, TrendSignal
from app.pipeline.scan import MAX_ERROR_LEN, finish_run, start_run

logger = logging.getLogger(__name__)
SOURCE = "etsy_counts"
MAX_KEYWORDS = 30
REFRESH_DAYS = 3  # skip keywords counted this recently
MAX_CONSECUTIVE_FAILURES = 3
FATAL_STATUSES = {401, 403}


def pick_keywords(session: Session, today: date, limit: int = MAX_KEYWORDS) -> list[tuple[int, str]]:
    """Top-scored POD keywords (latest scores) without a recent "<kw> shirt" count."""
    latest = session.scalar(select(func.max(KeywordScore.date)))
    if latest is None:
        return []
    fresh = select(TrendSignal.keyword_id).where(
        TrendSignal.source == "etsy", TrendSignal.metric == "listing_count_tshirt",
        TrendSignal.date > today - timedelta(days=REFRESH_DAYS),
    )
    return list(session.execute(
        select(Keyword.id, Keyword.text)
        .join(KeywordScore, KeywordScore.keyword_id == Keyword.id)
        .where(KeywordScore.date == latest, Keyword.is_pod_relevant.is_(True), Keyword.id.not_in(fresh))
        .order_by(KeywordScore.score.desc(), Keyword.id)
        .limit(limit)
    ).all())


def _store(session: Session, keyword_id: int, metric: str, value: float, today: date) -> None:
    row = session.scalar(select(TrendSignal).where(
        TrendSignal.keyword_id == keyword_id, TrendSignal.source == "etsy",
        TrendSignal.metric == metric, TrendSignal.date == today,
    ))
    if row is None:
        session.add(TrendSignal(keyword_id=keyword_id, source="etsy", metric=metric, value=value, date=today))
    else:
        row.value = value


async def run_etsy_counts(
    session_factory: sessionmaker[Session],
    api_key: str,
    today: date,
    *,
    min_interval: float = 0.2,
    sleep: Sleep = asyncio.sleep,
) -> int:
    run_id = start_run(session_factory, SOURCE)
    with session_factory() as session:
        keywords = pick_keywords(session, today)
    limiter = RateLimiter(min_interval, sleep=sleep)
    stored, errors, failures_in_a_row = 0, [], 0
    status = "ok"
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, headers={"x-api-key": api_key}, timeout=30.0) as client:
            for keyword_id, text in keywords:
                counts: dict[str, float] = {}
                for product_type, suffix in QUERY_SUFFIXES.items():
                    query = f"{text} {suffix}"
                    try:
                        resp = await request_with_retry(
                            client, "GET", "/listings/active", limiter=limiter, sleep=sleep,
                            params={"keywords": query, "limit": 1},
                        )
                        count = resp.json().get("count")
                    except (ConnectorError, ValueError, AttributeError) as exc:
                        errors.append(f"{query}: {exc}")
                        failures_in_a_row += 1
                        if getattr(exc, "status", None) in FATAL_STATUSES or failures_in_a_row >= MAX_CONSECUTIVE_FAILURES:
                            raise
                        continue
                    failures_in_a_row = 0
                    if isinstance(count, int | float):
                        counts[f"listing_count_{product_type}"] = float(count)
                if counts:
                    with session_factory() as session:
                        for metric, value in counts.items():
                            _store(session, keyword_id, metric, value, today)
                        session.commit()
                    stored += 1
    except Exception as exc:  # stop early; keep what was stored
        logger.warning("Etsy counts stopped: %s", type(exc).__name__)
        status = "partial" if stored else "failed"
        if not errors:
            errors.append(f"{type(exc).__name__}: {exc}")
    else:
        if errors:
            status = "partial" if stored else "failed"
    finish_run(session_factory, run_id, SOURCE, status, stored,
               "\n".join(errors)[:MAX_ERROR_LEN] if errors else None)
    return run_id
