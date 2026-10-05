from datetime import datetime

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
