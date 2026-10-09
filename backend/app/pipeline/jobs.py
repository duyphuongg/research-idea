from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.pipeline.etsy_counts import SOURCE as ETSY_COUNTS, run_etsy_counts
from app.pipeline.nfl import SOURCE as NFL, run_nfl
from app.pipeline.listing_signals import SOURCE as ETSY_SIGNALS, run_listing_signals


@dataclass(frozen=True)
class ScanJob:
    name: str
    run: Callable[[sessionmaker[Session], list[str], date], Awaitable[int]]


JobFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[ScanJob]]


def build_jobs(
    settings: Settings, overrides: dict[str, bool], only: list[str] | None = None
) -> list[ScanJob]:
    key = settings.etsy_api_key
    jobs = [
        ScanJob(ETSY_SIGNALS, lambda sf, kw, today: run_listing_signals(sf, key, kw, today)),
        ScanJob(ETSY_COUNTS, lambda sf, kw, today: run_etsy_counts(sf, key, today)),
    ] if key else []
    jobs.append(ScanJob(NFL, lambda sf, kw, today: run_nfl(sf, key, today)))  # Etsy demand only with a key
    return [
        job for job in jobs
        if overrides.get(job.name, True) and (only is None or job.name in only)
    ]
