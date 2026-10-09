from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
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


class Shop(Base):
    """A US Etsy shop seen in a listing payload; id is Etsy's shop_id."""

    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    first_seen: Mapped[date] = mapped_column(Date)
    last_seen: Mapped[date] = mapped_column(Date)
    watched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # watchlist flag

    snapshots: Mapped[list["ShopSnapshot"]] = relationship(
        order_by="ShopSnapshot.date", back_populates="shop"
    )


class ShopSnapshot(Base):
    """One per shop per UTC date; a later scan the same day overwrites it."""

    __tablename__ = "shop_snapshots"
    __table_args__ = (UniqueConstraint("shop_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"))
    date: Mapped[date] = mapped_column(Date)
    sold_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    listing_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    shop: Mapped[Shop] = relationship(back_populates="snapshots")


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
    tags: Mapped[Any] = mapped_column(JSON, nullable=True)
    licensed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    shop_id: Mapped[int | None] = mapped_column(ForeignKey("shops.id"), nullable=True, index=True)

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


class ListingSignal(Base):
    """Daily-tracked newly created Etsy listing (Listing Signals)."""

    __tablename__ = "listing_signals"

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    discovered_on: Mapped[date] = mapped_column(Date)
    discovery_query: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="calibrating")
    age_days: Mapped[int | None] = mapped_column(Integer)
    views: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    delta_views: Mapped[float | None] = mapped_column(Float)
    delta_saves: Mapped[float | None] = mapped_column(Float)
    dsr: Mapped[float | None] = mapped_column(Float)
    updated_on: Mapped[date | None] = mapped_column(Date)


class AmazonRank(Base):
    """Daily Amazon list rank of a product within a category. Historical only: Amazon is no longer scanned."""

    __tablename__ = "amazon_ranks"
    __table_args__ = (UniqueConstraint("product_id", "date", "category_key", "list_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    date: Mapped[date] = mapped_column(Date)
    category_key: Mapped[str] = mapped_column(String(40))
    list_name: Mapped[str] = mapped_column(String(20))
    rank: Mapped[int] = mapped_column(Integer)


class Alert(Base):
    """Something worth telling the user after a scan (Tin mới page + Telegram)."""

    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_kind_subject_created", "kind", "subject_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # niche | listing | hot_product (old "amazon" rows were dropped)
    subject_id: Mapped[int] = mapped_column(Integer)  # keyword id (niche) or product id
    level: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[float] = mapped_column(Float, default=0.0)  # higher = more important within a kind
    title: Mapped[str] = mapped_column(String(300))
    reason: Mapped[str] = mapped_column(String(300))
    image_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    link: Mapped[str] = mapped_column(String(300))  # in-app path
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    watch_keyword: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scan_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkItem(Base):
    """The user's own progress on a niche (keyword) or a listing (product)."""

    __tablename__ = "work_items"
    __table_args__ = (UniqueConstraint("subject_kind", "subject_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_kind: Mapped[str] = mapped_column(String(10))  # keyword | product
    subject_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # idea | designing | listed | skipped
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NflPerformance(Base):
    """A game leader (passing/rushing/receiving) from a finished NFL game (ESPN scoreboard)."""

    __tablename__ = "nfl_performances"
    __table_args__ = (
        UniqueConstraint("season", "season_type", "week", "event_id", "athlete_id", "category"),
        Index("ix_nfl_performances_week", "season", "season_type", "week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    season: Mapped[int] = mapped_column(Integer)
    season_type: Mapped[int] = mapped_column(Integer)  # 1 pre, 2 regular, 3 post
    week: Mapped[int] = mapped_column(Integer)
    event_id: Mapped[str] = mapped_column(String(20))
    game: Mapped[str] = mapped_column(String(200))
    game_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    athlete_id: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)
    jersey: Mapped[str | None] = mapped_column(String(5), nullable=True)
    team: Mapped[str | None] = mapped_column(String(10), nullable=True)
    category: Mapped[str] = mapped_column(String(30))  # passingYards | rushingYards | receivingYards
    stat_line: Mapped[str] = mapped_column(String(100))
    points: Mapped[float] = mapped_column(Float)
    headshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    player_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class NflPlayerDemand(Base):
    """Shirt demand for a player on a day: Etsy listings and Google apparel suggestions."""

    __tablename__ = "nfl_player_demand"
    __table_args__ = (UniqueConstraint("athlete_id", "date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    athlete_id: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date)
    etsy_listings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merch_suggestions: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NflPlayer(Base):
    """NFL roster entry (ESPN), refreshed weekly; used to recognise players in trending searches."""

    __tablename__ = "nfl_players"

    athlete_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(60))
    last_name: Mapped[str] = mapped_column(String(60))
    team: Mapped[str | None] = mapped_column(String(10), nullable=True)
    position: Mapped[str | None] = mapped_column(String(10), nullable=True)
    jersey: Mapped[str | None] = mapped_column(String(5), nullable=True)
    headshot_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_on: Mapped[date] = mapped_column(Date)


class NflMoment(Base):
    """An NFL-related US Google trending search (Khoảnh khắc NFL)."""

    __tablename__ = "nfl_moments"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(String(200), unique=True)
    traffic: Mapped[int] = mapped_column(Integer)  # highest approx traffic seen
    first_seen: Mapped[datetime] = mapped_column(DateTime)
    last_seen: Mapped[datetime] = mapped_column(DateTime)
    news: Mapped[Any] = mapped_column(JSON, default=list)  # [{title, url, source}]
    picture_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    athlete_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    team: Mapped[str | None] = mapped_column(String(10), nullable=True)
    etsy_listings: Mapped[int | None] = mapped_column(Integer, nullable=True)


class SportsTeam(Base):
    """NFL/MLB/NBA/NHL team names (ESPN), refreshed weekly; used by the IP-risk check."""

    __tablename__ = "sports_teams"
    __table_args__ = (UniqueConstraint("league", "abbreviation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    league: Mapped[str] = mapped_column(String(10))
    abbreviation: Mapped[str] = mapped_column(String(10))
    full_name: Mapped[str] = mapped_column(String(100))
    nickname: Mapped[str] = mapped_column(String(60))
    updated_on: Mapped[date] = mapped_column(Date)
