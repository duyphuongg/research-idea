from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.pipeline.listing_signals import SOURCE as ETSY_SIGNALS, run_listing_signals


@dataclass(frozen=True)
class ScanJob:
    name: str
    run: Callable[[sessionmaker[Session], list[str], date], Awaitable[int]]


JobFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[ScanJob]]


def build_jobs(
    settings: Settings, overrides: dict[str, bool], only: list[str] | None = None
) -> list[ScanJob]:
    if not settings.etsy_api_key:
        return []
    if not overrides.get(ETSY_SIGNALS, True):
        return []
    if only is not None and ETSY_SIGNALS not in only:
        return []
    return [
        ScanJob(
            ETSY_SIGNALS,
            lambda sf, kw, today: run_listing_signals(sf, settings.etsy_api_key, kw, today),
        )
    ]
