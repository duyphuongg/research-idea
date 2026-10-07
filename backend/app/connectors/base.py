from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol


class ConnectorError(Exception):
    """A connector request failed after retries."""

    def __init__(self, message: str = "", status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass
class RawBatch:
    source: str
    payloads: list[dict[str, Any]]  # JSON-serializable, stored verbatim in raw_payloads
    errors: list[str] = field(default_factory=list)  # per-query failures (partial scan)


@dataclass
class NormalizedProduct:
    source: str
    external_id: str
    title: str
    url: str
    image_url: str | None
    shop_name: str | None
    price: float | None
    currency: str | None
    product_type: str
    listed_at: datetime | None  # naive UTC
    keyword: str | None
    rank: int
    reviews: int | None = None
    favorites: int | None = None
    rating: float | None = None
    bsr: int | None = None
    views: int | None = None
    shop_sold_count: int | None = None
    tags: list[str] | None = None
    licensed: bool | None = None


@dataclass
class NormalizedSignal:
    keyword: str
    source: str
    metric: str
    value: float
    date: date
    origin: str = "seed"
    parent: str | None = None  # seed keyword this niche was discovered from


@dataclass
class NormalizedRank:
    external_id: str
    category_key: str
    list_name: str
    rank: int
    date: date


@dataclass
class NormalizedBatch:
    products: list[NormalizedProduct] = field(default_factory=list)
    signals: list[NormalizedSignal] = field(default_factory=list)
    ranks: list[NormalizedRank] = field(default_factory=list)


class Connector(Protocol):
    name: str
    kind: str  # "trend" | "product" | "both"

    def enabled(self) -> bool: ...

    async def fetch(self, keywords: list[str]) -> RawBatch: ...

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch: ...
