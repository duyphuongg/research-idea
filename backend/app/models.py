from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, utcnow


class Seed(Base):
    __tablename__ = "seeds"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(200), unique=True)
    origin: Mapped[str] = mapped_column(String(20))  # seed | discovered
    is_pod_relevant: Mapped[bool] = mapped_column(Boolean, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrendSignal(Base):
    __tablename__ = "trend_signals"
    __table_args__ = (UniqueConstraint("keyword_id", "source", "metric", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"))
    source: Mapped[str] = mapped_column(String(30))
    metric: Mapped[str] = mapped_column(String(50))
    value: Mapped[float] = mapped_column(Float)
    date: Mapped[date] = mapped_column(Date)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("source", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    shop_name: Mapped[str | None] = mapped_column(String(200))
    price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(3))
    product_type: Mapped[str] = mapped_column(String(20))  # tshirt | sweatshirt | hoodie
    listed_at: Mapped[datetime | None] = mapped_column(DateTime)
    shop_sold_count: Mapped[int | None] = mapped_column(Integer)

    snapshots: Mapped[list["ProductSnapshot"]] = relationship(
        order_by="ProductSnapshot.date", back_populates="product"
    )


class ProductKeyword(Base):
    __tablename__ = "product_keywords"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[date] = mapped_column(Date)


class ProductSnapshot(Base):
    __tablename__ = "product_snapshots"
    __table_args__ = (UniqueConstraint("product_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    date: Mapped[date] = mapped_column(Date)
    reviews: Mapped[int | None] = mapped_column(Integer)
    favorites: Mapped[int | None] = mapped_column(Integer)
    rating: Mapped[float | None] = mapped_column(Float)
    bsr: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float | None] = mapped_column(Float)

    product: Mapped[Product] = relationship(back_populates="snapshots")


class ScanRun(Base):
    __tablename__ = "scan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(10), default="running")  # running|ok|partial|failed
    records: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


class RawPayload(Base):
    __tablename__ = "raw_payloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    scan_run_id: Mapped[int] = mapped_column(ForeignKey("scan_runs.id"))
    source: Mapped[str] = mapped_column(String(30))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    payload: Mapped[Any] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class KeywordRelation(Base):
    """parent (seed) → child (niche discovered from tags/suggestions)."""

    __tablename__ = "keyword_relations"

    parent_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"), primary_key=True)
    source: Mapped[str] = mapped_column(String(30), primary_key=True)
    last_seen: Mapped[date] = mapped_column(Date)


class KeywordScore(Base):
    __tablename__ = "keyword_scores"
    __table_args__ = (UniqueConstraint("keyword_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id"))
    score: Mapped[float] = mapped_column(Float)
    demand: Mapped[float | None] = mapped_column(Float)
    momentum: Mapped[float | None] = mapped_column(Float)
    competition: Mapped[float | None] = mapped_column(Float)
    growth: Mapped[float | None] = mapped_column(Float)
    sources_rising: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[Any] = mapped_column(JSON, default=list)
    date: Mapped[date] = mapped_column(Date)
