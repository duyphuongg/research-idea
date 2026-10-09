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
    licensed: bool | None = None


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
    listing_count: int | None = None  # Etsy results for "<kw> shirt"
    competition_level: Literal["low", "medium", "high"] | None = None
    opportunity: float | None = None


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
    order_by: date | None
    theme_words: list[str]
    seed_ideas: list[CalendarIdea]
    radar_matches: list[CalendarMatch]


class CalendarPage(BaseModel):
    today: date
    fulfillment_days: int
    events: list[CalendarEventOut]


class SignalTag(BaseModel):
    tag: str
    keyword_id: int | None


class SignalItem(BaseModel):
    product_id: int
    title: str
    url: str
    image_url: str | None
    shop_name: str | None
    shop_sold_count: int | None
    price: float | None
    currency: str | None
    product_type: str
    listed_at: datetime | None
    age_days: int | None
    views: int | None
    saves: int | None
    delta_views: float | None
    delta_saves: float | None
    dsr: float | None
    status: str
    discovery_query: str
    tags: list[SignalTag]


class SignalPage(BaseModel):
    updated_on: date | None
    counts: dict[str, int]
    total: int
    items: list[SignalItem]


class AlertOut(BaseModel):
    id: int
    kind: str
    level: int
    title: str
    reason: str
    image_url: str | None
    link: str
    external_url: str | None
    watch_keyword: str | None
    scan_date: date
    created_at: datetime
    read: bool


class AlertPage(BaseModel):
    unread: int
    items: list[AlertOut]


class UnreadCount(BaseModel):
    unread: int


class TelegramStatus(BaseModel):
    configured: bool
    app_url: str | None


class WatchChild(BaseModel):
    keyword_id: int
    keyword: str
    score: float


class WatchThumb(BaseModel):
    product_id: int
    image_url: str | None
    title: str
    url: str
    status: str


class WatchItem(BaseModel):
    seed_id: int
    keyword: str
    keyword_id: int | None
    score: float | None
    growth: float | None
    children_total: int
    children: list[WatchChild]
    listings: dict[str, int]
    thumbnails: list[WatchThumb]
    alerts_7d: int


class WatchPage(BaseModel):
    date: date | None
    items: list[WatchItem]


class DeltaOut(BaseModel):
    value: int
    days: int


class ShopOut(BaseModel):
    id: int
    name: str
    url: str | None
    icon_url: str | None
    opened_year: int | None
    listing_count: int | None
    sold_count: int | None
    sales_7d: DeltaOut | None
    sales_30d: DeltaOut | None
    favorers_7d: DeltaOut | None
    sales_per_listing: float | None
    review_average: float | None
    review_count: int | None
    watched: bool
    last_seen: date


class ShopPage(BaseModel):
    total: int
    latest_date: date | None
    items: list[ShopOut]


class ShopPoint(BaseModel):
    date: date
    sold_count: int | None
    favorers: int | None


class ShopDetail(ShopOut):
    series: list[ShopPoint]
    products: list[ProductOut]


WorkStatus = Literal["idea", "designing", "listed", "skipped"]


class WorkIn(BaseModel):
    status: WorkStatus
    note: str | None = Field(default=None, max_length=500)

    @field_validator("note")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class WorkOut(BaseModel):
    subject_kind: Literal["keyword", "product"]
    subject_id: int
    status: WorkStatus
    note: str | None
    updated_at: datetime
    title: str
    image_url: str | None
    link: str | None
    external_url: str | None


class NicheCompetition(BaseModel):
    date: date | None
    counts: dict[str, int]
    level: Literal["low", "medium", "high"] | None


class NichePrice(BaseModel):
    product_type: str
    count: int
    p25: float
    median: float
    p75: float
    breakout_median: float | None


class NicheTag(BaseModel):
    tag: str
    listings: int
    breakouts: int
    share: float
    lift: float
    rising: bool


class NicheGenerated(BaseModel):
    tags: list[str]
    title_phrases: list[str]


class NicheReport(BaseModel):
    keyword: str
    keyword_id: int | None
    product_type: str | None
    listings: int
    breakouts: int
    competition: NicheCompetition
    prices: list[NichePrice]
    tags: list[NicheTag]
    generated: NicheGenerated


class NflWeek(BaseModel):
    season: int
    season_type: int
    week: int
    games: int


class NflLine(BaseModel):
    category: str
    stat_line: str


class NflStandout(BaseModel):
    athlete_id: str
    name: str
    position: str | None
    jersey: str | None
    team: str | None
    headshot_url: str | None
    player_url: str | None
    games: list[str]
    lines: list[NflLine]
    points: float
    performance: float
    etsy_listings: int | None
    merch_suggestions: int | None
    trending: bool
    potential: float


class NflPage(BaseModel):
    season: int | None
    season_type: int | None
    week: int | None
    weeks: list[NflWeek]
    items: list[NflStandout]


class NflMomentNews(BaseModel):
    title: str
    url: str | None = None
    source: str | None = None


class NflMomentPlayer(BaseModel):
    athlete_id: str
    name: str
    team: str | None
    position: str | None
    headshot_url: str | None


class NflMomentOut(BaseModel):
    id: int
    query: str
    traffic: int
    first_seen: datetime
    last_seen: datetime
    news: list[NflMomentNews]
    picture_url: str | None
    etsy_listings: int | None
    team: str | None
    player: NflMomentPlayer | None


class NflMomentsPage(BaseModel):
    items: list[NflMomentOut]
