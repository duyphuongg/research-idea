from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductOut(BaseModel):
    id: int
    source: str
    title: str
    url: str
    image_url: str | None
    shop_name: str | None
    price: float | None
    currency: str | None
    product_type: str
    listed_at: datetime | None
    reviews: int | None
    favorites: int | None
    rating: float | None
    views: int | None
    shop_sold_count: int | None
    velocity_metric: str | None
    delta_7d: float | None
    velocity: float | None
    hot: bool
    keywords: list[str]


class ProductPage(BaseModel):
    total: int
    items: list[ProductOut]


class SeedIn(BaseModel):
    keyword: str = Field(max_length=200)

    @field_validator("keyword")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("keyword must not be blank")
        return value


class SeedOut(BaseModel):
    id: int
    keyword: str
    active: bool
    created_at: datetime
    keyword_id: int


class ConnectorStatusOut(BaseModel):
    name: str
    kind: str
    configured: bool
    enabled: bool


class SettingsOut(BaseModel):
    scan_hour_utc: int
    connectors: list[ConnectorStatusOut]


class SettingsIn(BaseModel):
    scan_hour_utc: int | None = Field(None, ge=0, le=23)
    connectors_enabled: dict[str, bool] | None = None


class ScanIn(BaseModel):
    sources: list[str] | None = None


class ScanStarted(BaseModel):
    sources: list[str]


class ScanRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    records: int
    error: str | None


class SourceHealthOut(ConnectorStatusOut):
    last_status: str | None
    last_finished_at: datetime | None
    last_error: str | None


class TrendOut(BaseModel):
    keyword_id: int
    keyword: str
    origin: str
    is_pod_relevant: bool
    is_seed: bool
    is_new: bool
    score: float
    demand: float | None
    momentum: float | None
    competition: float | None
    growth: float | None
    sources: list[str]
    sources_rising: int
    sparkline: list[float]


class TrendPage(BaseModel):
    date: date | None
    items: list[TrendOut]


class SignalPoint(BaseModel):
    date: date
    value: float


class SignalSeries(BaseModel):
    source: str
    metric: str
    points: list[SignalPoint]


class RelatedKeywordOut(BaseModel):
    keyword_id: int
    keyword: str
    relation: Literal["child", "parent"]
    source: str
    score: float | None
    is_pod_relevant: bool


class TrendDetail(BaseModel):
    keyword_id: int
    keyword: str
    origin: str
    is_pod_relevant: bool
    is_seed: bool
    trend: TrendOut | None
    signals: list[SignalSeries]
    related: list[RelatedKeywordOut]


class CalendarIdea(BaseModel):
    keyword: str
    keyword_id: int | None
    score: float | None
    is_seed: bool


class CalendarMatch(BaseModel):
    keyword_id: int
    keyword: str
    score: float


class CalendarEventOut(BaseModel):
    key: str
    name: str
    type: str
    start: date
    end: date
    days_until: int
    phase: str
    phase_label: str
    advice: str
    note: str
    design_start: date
    launch_by: date
    push_from: date
    ship_by: date | None
    theme_words: list[str]
    seed_ideas: list[CalendarIdea]
    radar_matches: list[CalendarMatch]


class CalendarPage(BaseModel):
    today: date
    fulfillment_days: int
    events: list[CalendarEventOut]
