# POD Trend Radar — Phase 1 (Nền tảng + Etsy + Best Sellers) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dựng backend FastAPI + scan pipeline với connector Etsy, lưu snapshot sản phẩm hằng ngày, tính velocity/🔥, và dashboard Next.js gồm màn Best Sellers + Settings.

**Architecture:** Mỗi nguồn dữ liệu là một connector (`fetch` lấy raw → `normalize` hàm thuần). Scan pipeline chạy từng connector cô lập, lưu raw JSON, upsert sản phẩm + snapshot theo ngày, ghi `scan_runs`. API đọc DB, tính velocity khi truy vấn. Frontend là client components gọi REST API.

**Tech Stack:** Python 3.12 (qua `uv`), FastAPI, SQLAlchemy 2, Alembic, pydantic-settings, httpx, APScheduler 3.x, pytest + pytest-asyncio + respx; Next.js (App Router, TypeScript, Tailwind).

**Spec:** `docs/superpowers/specs/2026-10-05-pod-trend-radar-design.md` (Phase 1 = mục 11 bước 1). Phase 2 (Trend Radar) và Phase 3 có plan riêng.

## Global Constraints

- Python `>=3.12`; tạo venv bằng `uv venv .venv --python 3.12` (máy không có sẵn python3.12).
- Node 20 (đã có); Next.js qua `create-next-app@latest`.
- DB mặc định `sqlite:///./data/radar.db` (tương đối thư mục `backend/`); phải chuyển Postgres chỉ bằng đổi `DATABASE_URL`.
- Mọi datetime lưu dạng **naive UTC** (`datetime.now(timezone.utc).replace(tzinfo=None)`); frontend parse bằng cách thêm `Z`.
- Không gọi mạng trong pytest. Connector test bằng fixture JSON / respx.
- API key chỉ đọc từ `backend/.env`; không bao giờ trả API key về frontend (chỉ trả `configured: true/false`).
- Retry tối đa 3 lần (tổng 4 lần gọi), backoff `1s, 2s, 4s`; retry trên 429/5xx và lỗi transport; 4xx khác lỗi ngay.
- Raw payload giữ 30 ngày (`RAW_RETENTION_DAYS=30`).
- Sản phẩm "hot" = top 10% velocity theo (source, product_type); cần ≥ 2 snapshot cách nhau ≥ 3 ngày.
- UI tiếng Việt; dashboard phải ghi rõ reviews/favorites là **proxy**, không phải doanh số thật.
- Commit message kết thúc bằng dòng: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## File Structure

```
.gitignore
Makefile
README.md
backend/
  pyproject.toml
  .env.example
  alembic.ini
  alembic/env.py, alembic/versions/<rev>_initial_schema.py
  app/
    __init__.py
    config.py               # Settings (pydantic-settings)
    db.py                   # Base, make_engine, make_session_factory, utcnow
    models.py               # ORM tables
    keywords.py             # normalize_keyword, get_or_create_keyword
    settings_store.py       # get_setting / set_setting (bảng settings)
    scheduler.py            # APScheduler daily job
    main.py                 # create_app()
    connectors/
      __init__.py
      base.py               # RawBatch, Normalized*, Connector Protocol, ConnectorError
      http.py               # RateLimiter, request_with_retry
      etsy.py               # EtsyConnector
      registry.py           # make_all_connectors, build_connectors, connector_status
    analysis/
      __init__.py
      product_type.py       # classify_product_type
      velocity.py           # SnapshotPoint, compute_velocity, hot_ids
    pipeline/
      __init__.py
      store.py              # persist_batch
      scan.py               # run_scan, purge_raw_payloads
    services/
      __init__.py
      scans.py              # scan_in_progress, resolve_connectors, execute_scan
    api/
      __init__.py
      deps.py               # get_session
      schemas.py            # Pydantic response/request models
      products.py, seeds.py, settings.py, scans.py, health.py
  scripts/smoke.py
  tests/
    __init__.py, conftest.py, fakes.py
    fixtures/etsy/payload_nurse_shirt.json
    test_app.py, test_models.py, test_migrations.py, test_http.py,
    test_product_type.py, test_etsy.py, test_store.py, test_scan.py,
    test_velocity.py, test_api_products.py, test_api_seeds_settings.py,
    test_scheduler.py, test_api_scans_health.py
frontend/
  .env.local.example
  app/layout.tsx, app/globals.css, app/page.tsx,
  app/products/page.tsx, app/settings/page.tsx
  components/ProductCard.tsx, components/SourceHealthBanner.tsx
  lib/api.ts, lib/format.ts
```

---

### Task 1: Backend scaffold

**Files:**
- Create: `.gitignore`, `Makefile`, `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`
- Test: `backend/tests/test_app.py`

**Interfaces:**
- Produces: `Settings` (fields `database_url`, `etsy_api_key`, `scheduler_enabled`, `raw_retention_days`, `cors_origins`), `get_settings()`, `Base`, `make_engine(url)`, `make_session_factory(engine)`, `utcnow()`, `create_app(settings=None, session_factory=None)`; pytest fixtures `engine`, `session_factory`, `session`, `settings`, `make_client`, `client`.

- [ ] **Step 1: Create root `.gitignore`**

```gitignore
__pycache__/
*.pyc
backend/.venv/
backend/data/
backend/.env
backend/.pytest_cache/
backend/*.egg-info/
frontend/node_modules/
frontend/.next/
frontend/.env.local
.DS_Store
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "pod-trend-radar"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy>=2.0",
  "alembic>=1.13",
  "pydantic-settings>=2.4",
  "httpx>=0.27",
  "apscheduler>=3.10,<4",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "respx>=0.21"]

[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create `Makefile` (root) and install**

```makefile
.PHONY: install migrate dev-backend test smoke

install:
	cd backend && uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python -e ".[dev]"

migrate:
	cd backend && .venv/bin/alembic upgrade head

dev-backend:
	cd backend && .venv/bin/uvicorn --factory app.main:create_app --reload --port 8000

test:
	cd backend && .venv/bin/pytest -q

smoke:
	cd backend && .venv/bin/python scripts/smoke.py
```

Run: `make install`
Expected: venv tạo ở `backend/.venv`, cài đặt thành công.

- [ ] **Step 4: Create `backend/.env.example`**

```dotenv
# Copy thành backend/.env rồi điền giá trị thật
DATABASE_URL=sqlite:///./data/radar.db
# Lấy tại https://www.etsy.com/developers/your-apps (định dạng theo hướng dẫn hiện hành của Etsy)
ETSY_API_KEY=
SCHEDULER_ENABLED=true
RAW_RETENTION_DAYS=30
CORS_ORIGINS=["http://localhost:3000"]
```

- [ ] **Step 5: Create `backend/app/__init__.py` (empty), `backend/app/config.py`**

```python
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/radar.db"
    etsy_api_key: str | None = None
    scheduler_enabled: bool = True
    raw_retention_days: int = 30
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 6: Create `backend/app/db.py`**

```python
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC timestamp; all datetimes in the DB are naive UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
```

- [ ] **Step 7: Create `backend/tests/__init__.py` (empty) and `backend/tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import Base, make_session_factory
from app.main import create_app


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return make_session_factory(engine)


@pytest.fixture
def session(session_factory):
    with session_factory() as s:
        yield s


@pytest.fixture
def settings():
    return Settings(
        database_url="sqlite://",
        etsy_api_key="test-key",
        scheduler_enabled=False,
        _env_file=None,
    )


@pytest.fixture
def make_client(settings, session_factory):
    clients = []

    def _make(**kwargs):
        c = TestClient(create_app(settings=settings, session_factory=session_factory, **kwargs))
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    return make_client()
```

- [ ] **Step 8: Write the failing test `backend/tests/test_app.py`**

```python
def test_ping(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_cors_allows_frontend_origin(client):
    resp = client.get("/api/ping", headers={"Origin": "http://localhost:3000"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
```

- [ ] **Step 9: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_app.py -v`
Expected: FAIL / ERROR — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 10: Create `backend/app/main.py`**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import make_engine, make_session_factory


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="POD Trend Radar", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    return app
```

- [ ] **Step 11: Run tests to verify they pass**

Run: `cd backend && .venv/bin/pytest -v`
Expected: 2 passed

- [ ] **Step 12: Commit**

```bash
git add .gitignore Makefile backend/pyproject.toml backend/.env.example backend/app backend/tests
git commit -m "feat(backend): scaffold FastAPI app, config and test fixtures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: ORM models, keyword helpers, Alembic migration

**Files:**
- Create: `backend/app/models.py`, `backend/app/keywords.py`, `backend/alembic.ini` (generated), `backend/alembic/env.py`, `backend/alembic/versions/<rev>_initial_schema.py` (generated)
- Modify: `backend/tests/conftest.py` (import models)
- Test: `backend/tests/test_models.py`, `backend/tests/test_migrations.py`

**Interfaces:**
- Consumes: `Base`, `utcnow`, `make_engine`, `get_settings` (Task 1)
- Produces: models `Seed, Keyword, TrendSignal, Product, ProductKeyword, ProductSnapshot, ScanRun, RawPayload, Setting` (cột như Step 3); `Product.snapshots` sắp theo `date` tăng dần; `normalize_keyword(text: str) -> str`; `get_or_create_keyword(session, text: str, origin: str = "seed") -> Keyword`.

- [ ] **Step 1: Write the failing test `backend/tests/test_models.py`**

```python
from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import Product, ProductSnapshot


def test_normalize_keyword_lowercases_and_collapses_spaces():
    assert normalize_keyword("  Dog   MOM ") == "dog mom"


def test_get_or_create_keyword_is_idempotent(session):
    a = get_or_create_keyword(session, "Dog Mom")
    b = get_or_create_keyword(session, "dog  mom")
    assert a.id == b.id
    assert a.text == "dog mom"
    assert a.origin == "seed"


def test_product_snapshots_ordered_by_date(session):
    p = Product(source="etsy", external_id="1", title="T", url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add_all(
        [
            ProductSnapshot(product_id=p.id, date=date(2026, 9, 27), favorites=2),
            ProductSnapshot(product_id=p.id, date=date(2026, 9, 20), favorites=1),
        ]
    )
    session.commit()
    session.refresh(p)
    assert [s.date for s in p.snapshots] == [date(2026, 9, 20), date(2026, 9, 27)]


def test_product_unique_per_source_external_id(session):
    session.add(Product(source="etsy", external_id="1", title="A", url="u", product_type="tshirt"))
    session.add(Product(source="etsy", external_id="1", title="B", url="u", product_type="tshirt"))
    with pytest.raises(IntegrityError):
        session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_models.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.keywords'`

- [ ] **Step 3: Create `backend/app/models.py`**

```python
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
```

- [ ] **Step 4: Create `backend/app/keywords.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Keyword


def normalize_keyword(text: str) -> str:
    return " ".join(text.lower().split())


def get_or_create_keyword(session: Session, text: str, origin: str = "seed") -> Keyword:
    norm = normalize_keyword(text)
    keyword = session.scalar(select(Keyword).where(Keyword.text == norm))
    if keyword is None:
        keyword = Keyword(text=norm, origin=origin)
        session.add(keyword)
        session.flush()
    return keyword
```

- [ ] **Step 5: Register models in `backend/tests/conftest.py`** — add after the existing imports:

```python
import app.models  # noqa: F401  (registers tables on Base.metadata)
```

- [ ] **Step 6: Run model tests**

Run: `cd backend && .venv/bin/pytest tests/test_models.py -v`
Expected: 4 passed

- [ ] **Step 7: Init Alembic**

Run: `cd backend && .venv/bin/alembic init alembic`
Then in `backend/alembic.ini` change the line `sqlalchemy.url = driver://user:pass@localhost/dbname` to:

```ini
sqlalchemy.url =
```

- [ ] **Step 8: Replace `backend/alembic/env.py` entirely**

```python
from logging.config import fileConfig

from alembic import context

import app.models  # noqa: F401  (registers tables)
from app.config import get_settings
from app.db import Base, make_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 9: Write the failing test `backend/tests/test_migrations.py`**

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_migrations_create_every_model_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False

    command.upgrade(cfg, "head")

    tables = set(inspect(create_engine(url)).get_table_names())
    assert set(Base.metadata.tables) <= tables
```

- [ ] **Step 10: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_migrations.py -v`
Expected: FAIL — assertion (no tables besides `alembic_version`, since no revision exists yet)

- [ ] **Step 11: Generate the initial migration**

Run: `cd backend && .venv/bin/alembic revision --autogenerate -m "initial schema"`
Expected: `Generating .../alembic/versions/<rev>_initial_schema.py ... done`, and the file contains `op.create_table` for all 9 tables. Delete the dev DB it may have touched: `rm -f backend/data/radar.db`.

- [ ] **Step 12: Run all tests**

Run: `cd backend && .venv/bin/pytest -v`
Expected: all passed (7 tests)

- [ ] **Step 13: Commit**

```bash
git add backend/app/models.py backend/app/keywords.py backend/alembic.ini backend/alembic backend/tests
git commit -m "feat(backend): add ORM models, keyword helpers and initial migration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Connector contracts + HTTP retry / rate limiting

**Files:**
- Create: `backend/app/connectors/__init__.py` (empty), `backend/app/connectors/base.py`, `backend/app/connectors/http.py`
- Test: `backend/tests/test_http.py`

**Interfaces:**
- Produces:
  - `RawBatch(source: str, payloads: list[dict], errors: list[str] = [])`
  - `NormalizedProduct(source, external_id, title, url, image_url, shop_name, price, currency, product_type, listed_at: datetime|None, keyword, rank, reviews=None, favorites=None, rating=None, bsr=None)`
  - `NormalizedSignal(keyword, source, metric, value: float, date: date, origin="seed")`
  - `NormalizedBatch(products: list[NormalizedProduct] = [], signals: list[NormalizedSignal] = [])`
  - `Connector` Protocol: `name: str`, `kind: str`, `enabled() -> bool`, `async fetch(keywords: list[str]) -> RawBatch`, `normalize(raw: RawBatch, today: date) -> NormalizedBatch`
  - `ConnectorError(Exception)`
  - `RateLimiter(min_interval: float, *, clock=time.monotonic, sleep=asyncio.sleep)` with `async wait()`
  - `async request_with_retry(client: httpx.AsyncClient, method: str, url: str, *, retries=3, backoff=1.0, sleep=asyncio.sleep, limiter: RateLimiter|None=None, **kwargs) -> httpx.Response`

- [ ] **Step 1: Create `backend/app/connectors/base.py`**

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol


class ConnectorError(Exception):
    """A connector request failed after retries."""


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
    keyword: str
    rank: int
    reviews: int | None = None
    favorites: int | None = None
    rating: float | None = None
    bsr: int | None = None


@dataclass
class NormalizedSignal:
    keyword: str
    source: str
    metric: str
    value: float
    date: date
    origin: str = "seed"


@dataclass
class NormalizedBatch:
    products: list[NormalizedProduct] = field(default_factory=list)
    signals: list[NormalizedSignal] = field(default_factory=list)


class Connector(Protocol):
    name: str
    kind: str  # "trend" | "product" | "both"

    def enabled(self) -> bool: ...

    async def fetch(self, keywords: list[str]) -> RawBatch: ...

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch: ...
```

- [ ] **Step 2: Write the failing test `backend/tests/test_http.py`**

```python
import httpx
import pytest
import respx

from app.connectors.base import ConnectorError
from app.connectors.http import RateLimiter, request_with_retry

URL = "https://api.example.com/items"


class SleepRecorder:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


@respx.mock
async def test_retries_on_503_then_succeeds():
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": 1})]
    )
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        resp = await request_with_retry(client, "GET", URL, sleep=sleep)
    assert resp.json() == {"ok": 1}
    assert route.call_count == 3
    assert sleep.calls == [1.0, 2.0]


@respx.mock
async def test_gives_up_after_three_retries():
    route = respx.get(URL).mock(return_value=httpx.Response(429))
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        with pytest.raises(ConnectorError, match="HTTP 429"):
            await request_with_retry(client, "GET", URL, sleep=sleep)
    assert route.call_count == 4
    assert sleep.calls == [1.0, 2.0, 4.0]


@respx.mock
async def test_client_error_is_not_retried():
    route = respx.get(URL).mock(return_value=httpx.Response(404, text="nope"))
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        with pytest.raises(ConnectorError, match="HTTP 404"):
            await request_with_retry(client, "GET", URL, sleep=sleep)
    assert route.call_count == 1
    assert sleep.calls == []


@respx.mock
async def test_transport_error_is_retried():
    respx.get(URL).mock(side_effect=[httpx.ConnectError("down"), httpx.Response(200)])
    sleep = SleepRecorder()
    async with httpx.AsyncClient() as client:
        resp = await request_with_retry(client, "GET", URL, sleep=sleep)
    assert resp.status_code == 200
    assert sleep.calls == [1.0]


async def test_rate_limiter_waits_between_calls():
    sleep = SleepRecorder()
    limiter = RateLimiter(0.5, clock=lambda: 10.0, sleep=sleep)
    await limiter.wait()
    await limiter.wait()
    assert sleep.calls == [0.5]


async def test_rate_limiter_skips_wait_when_interval_elapsed():
    sleep = SleepRecorder()
    ticks = iter([0.0, 1.0, 1.0])
    limiter = RateLimiter(0.5, clock=lambda: next(ticks), sleep=sleep)
    await limiter.wait()
    await limiter.wait()
    assert sleep.calls == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_http.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.connectors.http'`

- [ ] **Step 4: Create `backend/app/connectors/http.py`**

```python
import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.connectors.base import ConnectorError

RETRY_STATUS = {429, 500, 502, 503, 504}

Sleep = Callable[[float], Awaitable[Any]]


class RateLimiter:
    """Enforces a minimum interval between consecutive requests."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            if self._last is not None:
                remaining = self.min_interval - (self._clock() - self._last)
                if remaining > 0:
                    await self._sleep(remaining)
            self._last = self._clock()


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    retries: int = 3,
    backoff: float = 1.0,
    sleep: Sleep = asyncio.sleep,
    limiter: RateLimiter | None = None,
    **kwargs: Any,
) -> httpx.Response:
    attempt = 0
    while True:
        if limiter is not None:
            await limiter.wait()
        try:
            resp = await client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            if attempt >= retries:
                raise ConnectorError(f"{method} {url}: {exc!r}") from exc
        else:
            if resp.status_code not in RETRY_STATUS:
                if resp.is_error:
                    raise ConnectorError(
                        f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]}"
                    )
                return resp
            if attempt >= retries:
                raise ConnectorError(
                    f"{method} {url}: HTTP {resp.status_code} after {retries} retries"
                )
        await sleep(backoff * 2**attempt)
        attempt += 1
```

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_http.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/connectors backend/tests/test_http.py
git commit -m "feat(connectors): add connector contracts, retry and rate limiter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Product type classifier + Etsy connector

**Files:**
- Create: `backend/app/analysis/__init__.py` (empty), `backend/app/analysis/product_type.py`, `backend/app/connectors/etsy.py`, `backend/tests/fixtures/etsy/payload_nurse_shirt.json`
- Test: `backend/tests/test_product_type.py`, `backend/tests/test_etsy.py`

**Interfaces:**
- Consumes: `RawBatch`, `NormalizedBatch`, `NormalizedProduct`, `NormalizedSignal`, `ConnectorError`, `RateLimiter`, `request_with_retry` (Task 3)
- Produces: `classify_product_type(title: str) -> Literal["tshirt","sweatshirt","hoodie","other"]`; `EtsyConnector(api_key: str | None, *, min_interval: float = 0.2, sleep=asyncio.sleep)` with `name="etsy"`, `kind="product"`. Raw payload shape: `{"keyword", "query", "product_type", "search": <listings/active JSON>, "details": <listings/batch JSON>}`. Signal metric: `listing_count_<product_type>`.

- [ ] **Step 1: Write the failing test `backend/tests/test_product_type.py`**

```python
import pytest

from app.analysis.product_type import classify_product_type


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Funny Nurse Shirt, Nurse Hoodie", "tshirt"),  # earliest mention wins
        ("Retro Dog Mom Sweatshirt", "sweatshirt"),
        ("Fishing Hooded Sweatshirt", "hoodie"),
        ("Comfort Colors Teacher Tee", "tshirt"),
        ("Christmas T-Shirt for Family", "tshirt"),
        ("Halloween Crewneck", "sweatshirt"),
        ("Pickleball HOODIES Gift", "hoodie"),
        ("Nurse Coffee Mug", "other"),
        ("Teepee Tent Decor", "other"),
    ],
)
def test_classify_product_type(title, expected):
    assert classify_product_type(title) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_product_type.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.analysis'`

- [ ] **Step 3: Create `backend/app/analysis/product_type.py`**

```python
import re
from typing import Literal

ProductType = Literal["tshirt", "sweatshirt", "hoodie", "other"]

_PATTERNS: dict[str, re.Pattern[str]] = {
    "hoodie": re.compile(r"\b(hoodies?|hooded)\b"),
    "sweatshirt": re.compile(r"\b(sweatshirts?|crew ?necks?)\b"),
    "tshirt": re.compile(r"\b(t-?shirts?|tees?|shirts?)\b"),
}


def classify_product_type(title: str) -> ProductType:
    """Classify by the apparel word that appears first in the title."""
    text = title.lower()
    best: tuple[int, ProductType] | None = None
    for product_type, pattern in _PATTERNS.items():
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), product_type)  # type: ignore[assignment]
    return best[1] if best else "other"
```

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_product_type.py -v`
Expected: 9 passed

- [ ] **Step 5: Create fixture `backend/tests/fixtures/etsy/payload_nurse_shirt.json`**

```json
{
  "keyword": "nurse",
  "query": "nurse shirt",
  "product_type": "tshirt",
  "search": {
    "count": 12345,
    "results": [
      {
        "listing_id": 1001,
        "title": "Funny Nurse Shirt &amp; Gift",
        "price": {"amount": 2499, "divisor": 100, "currency_code": "USD"},
        "num_favorers": 532,
        "url": "https://www.etsy.com/listing/1001/funny-nurse-shirt",
        "creation_timestamp": 1756684800,
        "original_creation_timestamp": 1754006400,
        "shop_id": 11
      },
      {
        "listing_id": 1002,
        "title": "Nurse Coffee Mug",
        "price": {"amount": 1599, "divisor": 100, "currency_code": "USD"},
        "num_favorers": 40,
        "url": "https://www.etsy.com/listing/1002/nurse-mug",
        "creation_timestamp": 1756684800,
        "shop_id": 11
      },
      {
        "listing_id": 1003,
        "title": "Retro Nurse Hoodie, Nurse Life Sweatshirt",
        "price": {"amount": 3999, "divisor": 100, "currency_code": "USD"},
        "num_favorers": 87,
        "url": "https://www.etsy.com/listing/1003/retro-nurse-hoodie",
        "creation_timestamp": 1758000000,
        "shop_id": 12
      }
    ]
  },
  "details": {
    "count": 2,
    "results": [
      {
        "listing_id": 1001,
        "images": [{"url_570xN": "https://i.etsystatic.com/1001_570xN.jpg"}],
        "shop": {"shop_id": 11, "shop_name": "NurseLifeCo"}
      },
      {
        "listing_id": 1003,
        "images": [],
        "shop": {"shop_id": 12, "shop_name": "RetroScrubs"}
      }
    ]
  }
}
```

- [ ] **Step 6: Write the failing test `backend/tests/test_etsy.py`**

```python
import json
from datetime import date, datetime
from pathlib import Path

import httpx
import respx

from app.connectors.base import RawBatch
from app.connectors.etsy import EtsyConnector

FIXTURES = Path(__file__).parent / "fixtures" / "etsy"
SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
BATCH_URL = "https://openapi.etsy.com/v3/application/listings/batch"


def load_payload() -> dict:
    return json.loads((FIXTURES / "payload_nurse_shirt.json").read_text())


async def no_sleep(_seconds: float) -> None:
    return None


def test_enabled_requires_api_key():
    assert EtsyConnector("k").enabled() is True
    assert EtsyConnector(None).enabled() is False
    assert EtsyConnector("").enabled() is False


def test_normalize_maps_apparel_listings_and_drops_others():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    batch = EtsyConnector("k").normalize(raw, date(2026, 10, 5))

    assert [p.external_id for p in batch.products] == ["1001", "1003"]
    shirt, hoodie = batch.products
    assert shirt.title == "Funny Nurse Shirt & Gift"
    assert shirt.price == 24.99
    assert shirt.currency == "USD"
    assert shirt.favorites == 532
    assert shirt.reviews is None
    assert shirt.image_url == "https://i.etsystatic.com/1001_570xN.jpg"
    assert shirt.shop_name == "NurseLifeCo"
    assert shirt.product_type == "tshirt"
    assert shirt.listed_at == datetime(2025, 8, 1)
    assert shirt.keyword == "nurse"
    assert shirt.rank == 1
    assert hoodie.product_type == "hoodie"
    assert hoodie.rank == 3
    assert hoodie.image_url is None
    assert hoodie.listed_at is not None

    assert len(batch.signals) == 1
    signal = batch.signals[0]
    assert (signal.keyword, signal.source, signal.metric, signal.value, signal.date) == (
        "nurse", "etsy", "listing_count_tshirt", 12345.0, date(2026, 10, 5)
    )


@respx.mock
async def test_fetch_runs_search_and_batch_per_product_type():
    payload = load_payload()
    search = respx.get(url__startswith=SEARCH_URL).mock(
        return_value=httpx.Response(200, json=payload["search"])
    )
    batch = respx.get(url__startswith=BATCH_URL).mock(
        return_value=httpx.Response(200, json=payload["details"])
    )

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert [p["query"] for p in raw.payloads] == ["nurse shirt", "nurse sweatshirt", "nurse hoodie"]
    assert [p["product_type"] for p in raw.payloads] == ["tshirt", "sweatshirt", "hoodie"]
    assert raw.errors == []
    assert search.call_count == 3
    assert batch.call_count == 3
    first = search.calls[0].request
    assert first.headers["x-api-key"] == "k"
    assert first.url.params["keywords"] == "nurse shirt"
    assert batch.calls[0].request.url.params["listing_ids"] == "1001,1002,1003"


@respx.mock
async def test_fetch_collects_errors_per_query():
    respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404, text="nope"))

    raw = await EtsyConnector("k", min_interval=0, sleep=no_sleep).fetch(["nurse"])

    assert raw.payloads == []
    assert len(raw.errors) == 3
    assert all("HTTP 404" in e for e in raw.errors)
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_etsy.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.connectors.etsy'`

- [ ] **Step 8: Create `backend/app/connectors/etsy.py`**

```python
"""Etsy Open API v3: top apparel listings for each seed keyword."""

import asyncio
import html
from datetime import date, datetime, timezone
from typing import Any

import httpx

from app.analysis.product_type import classify_product_type
from app.connectors.base import (
    ConnectorError,
    NormalizedBatch,
    NormalizedProduct,
    NormalizedSignal,
    RawBatch,
)
from app.connectors.http import RateLimiter, Sleep, request_with_retry

BASE_URL = "https://openapi.etsy.com/v3/application"
# product_type -> suffix appended to the seed keyword for the search query
QUERY_SUFFIXES = {"tshirt": "shirt", "sweatshirt": "sweatshirt", "hoodie": "hoodie"}
SEARCH_LIMIT = 50


class EtsyConnector:
    name = "etsy"
    kind = "product"

    def __init__(
        self, api_key: str | None, *, min_interval: float = 0.2, sleep: Sleep = asyncio.sleep
    ) -> None:
        self.api_key = api_key
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)

    def enabled(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, keywords: list[str]) -> RawBatch:
        payloads: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(
            base_url=BASE_URL, headers={"x-api-key": self.api_key or ""}, timeout=30.0
        ) as client:
            for keyword in keywords:
                for product_type, suffix in QUERY_SUFFIXES.items():
                    query = f"{keyword} {suffix}"
                    try:
                        payloads.append(
                            await self._fetch_query(client, keyword, query, product_type)
                        )
                    except ConnectorError as exc:
                        errors.append(f"{query}: {exc}")
        return RawBatch(source=self.name, payloads=payloads, errors=errors)

    async def _fetch_query(
        self, client: httpx.AsyncClient, keyword: str, query: str, product_type: str
    ) -> dict[str, Any]:
        search = (
            await self._get(
                client,
                "/listings/active",
                {"keywords": query, "limit": SEARCH_LIMIT, "sort_on": "score"},
            )
        ).json()
        ids = [str(item["listing_id"]) for item in search.get("results", [])]
        details: dict[str, Any] = {"results": []}
        if ids:
            details = (
                await self._get(
                    client,
                    "/listings/batch",
                    {"listing_ids": ",".join(ids), "includes": "Images,Shop"},
                )
            ).json()
        return {
            "keyword": keyword,
            "query": query,
            "product_type": product_type,
            "search": search,
            "details": details,
        }

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, Any]
    ) -> httpx.Response:
        return await request_with_retry(
            client, "GET", path, params=params, limiter=self._limiter, sleep=self._sleep
        )

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        batch = NormalizedBatch()
        for payload in raw.payloads:
            keyword = payload["keyword"]
            search = payload.get("search", {})
            if search.get("count") is not None:
                batch.signals.append(
                    NormalizedSignal(
                        keyword=keyword,
                        source=self.name,
                        metric=f"listing_count_{payload['product_type']}",
                        value=float(search["count"]),
                        date=today,
                    )
                )
            details = {
                str(d["listing_id"]): d for d in payload.get("details", {}).get("results", [])
            }
            for rank, item in enumerate(search.get("results", []), start=1):
                listing = {**item, **details.get(str(item["listing_id"]), {})}
                product = _to_product(listing, keyword, rank)
                if product is not None:
                    batch.products.append(product)
        return batch


def _to_product(listing: dict[str, Any], keyword: str, rank: int) -> NormalizedProduct | None:
    title = html.unescape(listing.get("title") or "").strip()
    product_type = classify_product_type(title)
    if product_type == "other":
        return None
    price = listing.get("price") or {}
    amount = price.get("amount")
    divisor = price.get("divisor") or 1
    images = listing.get("images") or []
    shop = listing.get("shop") or {}
    created = listing.get("original_creation_timestamp") or listing.get("creation_timestamp")
    listing_id = str(listing["listing_id"])
    return NormalizedProduct(
        source="etsy",
        external_id=listing_id,
        title=title,
        url=listing.get("url") or f"https://www.etsy.com/listing/{listing_id}",
        image_url=images[0].get("url_570xN") if images else None,
        shop_name=shop.get("shop_name"),
        price=amount / divisor if amount is not None else None,
        currency=price.get("currency_code"),
        product_type=product_type,
        listed_at=(
            datetime.fromtimestamp(created, tz=timezone.utc).replace(tzinfo=None)
            if created
            else None
        ),
        keyword=keyword,
        rank=rank,
        favorites=listing.get("num_favorers"),
    )
```

- [ ] **Step 9: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_etsy.py tests/test_product_type.py -v`
Expected: all passed (13 tests)

- [ ] **Step 10: Commit**

```bash
git add backend/app/analysis backend/app/connectors/etsy.py backend/tests
git commit -m "feat(connectors): add product type classifier and Etsy connector

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Persist normalized batches

**Files:**
- Create: `backend/app/pipeline/__init__.py` (empty), `backend/app/pipeline/store.py`, `backend/tests/fakes.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: models (Task 2), `get_or_create_keyword` (Task 2), `NormalizedBatch/Product/Signal`, `RawBatch` (Task 3)
- Produces: `persist_batch(session, batch: NormalizedBatch, today: date) -> int` (số record đã ghi; không commit). Test helpers in `tests/fakes.py`: `make_product(**overrides) -> NormalizedProduct`, `FakeConnector(name="fake", products=None, errors=None, fail=False)` with attribute `received_keywords`.

- [ ] **Step 1: Create `backend/tests/fakes.py`**

```python
from datetime import date, datetime

from app.connectors.base import NormalizedBatch, NormalizedProduct, RawBatch


def make_product(**overrides) -> NormalizedProduct:
    values = dict(
        source="fake",
        external_id="1",
        title="Nurse Shirt",
        url="https://example.com/1",
        image_url=None,
        shop_name="Shop",
        price=19.99,
        currency="USD",
        product_type="tshirt",
        listed_at=datetime(2026, 9, 1),
        keyword="nurse",
        rank=1,
        favorites=10,
    )
    values.update(overrides)
    return NormalizedProduct(**values)


class FakeConnector:
    kind = "product"

    def __init__(self, name="fake", products=None, errors=None, fail=False):
        self.name = name
        self.products = [make_product()] if products is None else products
        self.errors = errors or []
        self.fail = fail
        self.received_keywords: list[str] | None = None

    def enabled(self) -> bool:
        return True

    async def fetch(self, keywords: list[str]) -> RawBatch:
        self.received_keywords = list(keywords)
        if self.fail:
            raise RuntimeError("boom")
        return RawBatch(source=self.name, payloads=[{"keywords": list(keywords)}], errors=list(self.errors))

    def normalize(self, raw: RawBatch, today: date) -> NormalizedBatch:
        return NormalizedBatch(products=list(self.products))
```

- [ ] **Step 2: Write the failing test `backend/tests/test_store.py`**

```python
from datetime import date

from sqlalchemy import func, select

from app.connectors.base import NormalizedBatch, NormalizedSignal
from app.models import Keyword, Product, ProductKeyword, ProductSnapshot, TrendSignal
from app.pipeline.store import persist_batch
from tests.fakes import make_product

D1 = date(2026, 9, 20)
D2 = date(2026, 9, 27)


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_persists_new_product_with_keyword_and_snapshot(session):
    written = persist_batch(session, NormalizedBatch(products=[make_product(rank=4)]), D1)
    session.commit()

    assert written == 1
    product = session.scalar(select(Product))
    assert (product.source, product.external_id, product.title) == ("fake", "1", "Nurse Shirt")
    keyword = session.scalar(select(Keyword))
    assert keyword.text == "nurse"
    link = session.get(ProductKeyword, (product.id, keyword.id))
    assert (link.rank, link.last_seen) == (4, D1)
    snapshot = session.scalar(select(ProductSnapshot))
    assert (snapshot.date, snapshot.favorites, snapshot.price) == (D1, 10, 19.99)


def test_same_day_is_upserted_and_keeps_best_rank(session):
    batch = NormalizedBatch(
        products=[make_product(rank=5, favorites=10), make_product(rank=2, favorites=12)]
    )
    persist_batch(session, batch, D1)
    session.commit()

    assert count(session, Product) == 1
    assert count(session, ProductSnapshot) == 1
    assert session.scalar(select(ProductSnapshot)).favorites == 12
    assert session.scalar(select(ProductKeyword)).rank == 2


def test_next_day_adds_snapshot_and_updates_fields(session):
    persist_batch(session, NormalizedBatch(products=[make_product(favorites=10)]), D1)
    persist_batch(
        session, NormalizedBatch(products=[make_product(favorites=30, title="New Title", rank=9)]), D2
    )
    session.commit()

    assert count(session, ProductSnapshot) == 2
    assert session.scalar(select(Product)).title == "New Title"
    assert session.scalar(select(ProductKeyword)).rank == 9


def test_signals_are_upserted_per_day(session):
    sig = NormalizedSignal(keyword="Nurse", source="etsy", metric="listing_count_tshirt", value=1.0, date=D1)
    persist_batch(session, NormalizedBatch(signals=[sig]), D1)
    sig2 = NormalizedSignal(keyword="nurse", source="etsy", metric="listing_count_tshirt", value=2.0, date=D1)
    written = persist_batch(session, NormalizedBatch(signals=[sig2]), D1)
    session.commit()

    assert written == 1
    assert count(session, TrendSignal) == 1
    assert session.scalar(select(TrendSignal)).value == 2.0
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_store.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 4: Create `backend/app/pipeline/store.py`**

```python
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import NormalizedBatch, NormalizedProduct, NormalizedSignal
from app.keywords import get_or_create_keyword
from app.models import Product, ProductKeyword, ProductSnapshot, TrendSignal


def persist_batch(session: Session, batch: NormalizedBatch, today: date) -> int:
    """Upsert signals, products, keyword links and today's snapshots. Does not commit."""
    for signal in batch.signals:
        _upsert_signal(session, signal)
    for item in batch.products:
        _upsert_product(session, item, today)
    session.flush()
    return len(batch.signals) + len(batch.products)


def _upsert_signal(session: Session, signal: NormalizedSignal) -> None:
    keyword = get_or_create_keyword(session, signal.keyword, signal.origin)
    row = session.scalar(
        select(TrendSignal).where(
            TrendSignal.keyword_id == keyword.id,
            TrendSignal.source == signal.source,
            TrendSignal.metric == signal.metric,
            TrendSignal.date == signal.date,
        )
    )
    if row is None:
        session.add(
            TrendSignal(
                keyword_id=keyword.id,
                source=signal.source,
                metric=signal.metric,
                value=signal.value,
                date=signal.date,
            )
        )
    else:
        row.value = signal.value
    session.flush()


def _upsert_product(session: Session, item: NormalizedProduct, today: date) -> None:
    product = session.scalar(
        select(Product).where(Product.source == item.source, Product.external_id == item.external_id)
    )
    if product is None:
        product = Product(source=item.source, external_id=item.external_id)
        session.add(product)
    product.title = item.title
    product.url = item.url
    product.image_url = item.image_url
    product.shop_name = item.shop_name
    product.price = item.price
    product.currency = item.currency
    product.product_type = item.product_type
    product.listed_at = item.listed_at
    session.flush()

    keyword = get_or_create_keyword(session, item.keyword)
    link = session.get(ProductKeyword, (product.id, keyword.id))
    if link is None:
        session.add(
            ProductKeyword(product_id=product.id, keyword_id=keyword.id, rank=item.rank, last_seen=today)
        )
    else:
        link.rank = min(link.rank, item.rank) if link.last_seen == today else item.rank
        link.last_seen = today

    snapshot = session.scalar(
        select(ProductSnapshot).where(
            ProductSnapshot.product_id == product.id, ProductSnapshot.date == today
        )
    )
    if snapshot is None:
        snapshot = ProductSnapshot(product_id=product.id, date=today)
        session.add(snapshot)
    snapshot.reviews = item.reviews
    snapshot.favorites = item.favorites
    snapshot.rating = item.rating
    snapshot.bsr = item.bsr
    snapshot.price = item.price
    session.flush()
```

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_store.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline backend/tests/fakes.py backend/tests/test_store.py
git commit -m "feat(pipeline): persist normalized products, snapshots and signals

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Scan pipeline + connector registry

**Files:**
- Create: `backend/app/pipeline/scan.py`, `backend/app/connectors/registry.py`
- Test: `backend/tests/test_scan.py`

**Interfaces:**
- Consumes: `persist_batch` (Task 5), `Connector` (Task 3), `EtsyConnector` (Task 4), `Settings` (Task 1), `FakeConnector` (tests)
- Produces:
  - `async run_scan(session_factory, connectors: list[Connector], *, today: date | None = None, retention_days: int = 30) -> list[int]` (scan_run ids; reads active `Seed` keywords)
  - `purge_raw_payloads(session, older_than: datetime) -> int`
  - `ConnectorFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[Connector]]`
  - `make_all_connectors(settings) -> list[Connector]`
  - `build_connectors(settings, enabled_overrides: dict[str, bool], only: list[str] | None = None) -> list[Connector]` (chỉ connector đã cấu hình + không bị tắt)
  - `connector_status(settings, enabled_overrides) -> list[dict]` với keys `name, kind, configured, enabled`

- [ ] **Step 1: Write the failing test `backend/tests/test_scan.py`**

```python
from datetime import date, timedelta

from sqlalchemy import func, select

from app.config import Settings
from app.connectors.registry import build_connectors, connector_status
from app.db import utcnow
from app.models import Product, ProductSnapshot, RawPayload, ScanRun, Seed
from app.pipeline.scan import run_scan
from tests.fakes import FakeConnector

TODAY = date(2026, 10, 5)


def add_seeds(session_factory, *keywords, inactive=()):
    with session_factory() as s:
        s.add_all([Seed(keyword=k) for k in keywords])
        s.add_all([Seed(keyword=k, active=False) for k in inactive])
        s.commit()


async def test_run_scan_persists_and_marks_ok(session_factory):
    add_seeds(session_factory, "nurse", "dog mom", inactive=["old"])
    fake = FakeConnector()

    [run_id] = await run_scan(session_factory, [fake], today=TODAY)

    assert fake.received_keywords == ["nurse", "dog mom"]
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert (run.source, run.status, run.records, run.error) == ("fake", "ok", 1, None)
        assert run.finished_at is not None
        assert s.scalar(select(func.count()).select_from(Product)) == 1
        assert s.scalar(select(ProductSnapshot)).date == TODAY
        assert s.scalar(select(RawPayload)).payload == {"keywords": ["nurse", "dog mom"]}


async def test_failing_connector_does_not_stop_others(session_factory):
    add_seeds(session_factory, "nurse")
    ids = await run_scan(
        session_factory, [FakeConnector(name="bad", fail=True), FakeConnector(name="good")], today=TODAY
    )

    with session_factory() as s:
        bad, good = (s.get(ScanRun, i) for i in ids)
        assert bad.status == "failed"
        assert "RuntimeError: boom" in bad.error
        assert good.status == "ok"


async def test_errors_with_payloads_mark_partial(session_factory):
    add_seeds(session_factory, "nurse")
    [run_id] = await run_scan(
        session_factory, [FakeConnector(errors=["nurse hoodie: HTTP 500"])], today=TODAY
    )

    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "partial"
        assert "HTTP 500" in run.error


async def test_old_raw_payloads_are_purged(session_factory):
    with session_factory() as s:
        run = ScanRun(source="fake", status="ok")
        s.add(run)
        s.flush()
        s.add(RawPayload(scan_run_id=run.id, source="fake", payload={}, fetched_at=utcnow() - timedelta(days=40)))
        s.add(RawPayload(scan_run_id=run.id, source="fake", payload={}, fetched_at=utcnow() - timedelta(days=1)))
        s.commit()

    await run_scan(session_factory, [], today=TODAY, retention_days=30)

    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(RawPayload)) == 1


def test_registry_filters_unconfigured_and_disabled():
    configured = Settings(etsy_api_key="k", _env_file=None)
    unconfigured = Settings(etsy_api_key=None, _env_file=None)

    assert [c.name for c in build_connectors(configured, {})] == ["etsy"]
    assert build_connectors(configured, {"etsy": False}) == []
    assert build_connectors(configured, {}, only=["amazon"]) == []
    assert build_connectors(unconfigured, {}) == []
    assert connector_status(unconfigured, {"etsy": False}) == [
        {"name": "etsy", "kind": "product", "configured": False, "enabled": False}
    ]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_scan.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.connectors.registry'`

- [ ] **Step 3: Create `backend/app/connectors/registry.py`**

```python
from collections.abc import Callable

from app.config import Settings
from app.connectors.base import Connector
from app.connectors.etsy import EtsyConnector

ConnectorFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[Connector]]


def make_all_connectors(settings: Settings) -> list[Connector]:
    return [EtsyConnector(api_key=settings.etsy_api_key)]


def build_connectors(
    settings: Settings, enabled_overrides: dict[str, bool], only: list[str] | None = None
) -> list[Connector]:
    return [
        c
        for c in make_all_connectors(settings)
        if c.enabled()
        and enabled_overrides.get(c.name, True)
        and (only is None or c.name in only)
    ]


def connector_status(settings: Settings, enabled_overrides: dict[str, bool]) -> list[dict]:
    return [
        {
            "name": c.name,
            "kind": c.kind,
            "configured": c.enabled(),
            "enabled": enabled_overrides.get(c.name, True),
        }
        for c in make_all_connectors(settings)
    ]
```

- [ ] **Step 4: Create `backend/app/pipeline/scan.py`**

```python
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.connectors.base import Connector
from app.db import utcnow
from app.models import RawPayload, ScanRun, Seed
from app.pipeline.store import persist_batch

logger = logging.getLogger(__name__)
MAX_ERROR_LEN = 5000


async def run_scan(
    session_factory: sessionmaker[Session],
    connectors: list[Connector],
    *,
    today: date | None = None,
    retention_days: int = 30,
) -> list[int]:
    today = today or datetime.now(timezone.utc).date()
    with session_factory() as session:
        keywords = list(
            session.scalars(select(Seed.keyword).where(Seed.active.is_(True)).order_by(Seed.id))
        )

    run_ids = [await _run_one(session_factory, c, keywords, today) for c in connectors]

    with session_factory() as session:
        purge_raw_payloads(session, older_than=utcnow() - timedelta(days=retention_days))
        session.commit()
    return run_ids


async def _run_one(
    session_factory: sessionmaker[Session], connector: Connector, keywords: list[str], today: date
) -> int:
    with session_factory() as session:
        run = ScanRun(source=connector.name, status="running")
        session.add(run)
        session.commit()
        run_id = run.id

    status, records, error = "ok", 0, None
    try:
        raw = await connector.fetch(keywords)
        normalized = connector.normalize(raw, today)
        with session_factory() as session:
            for payload in raw.payloads:
                session.add(RawPayload(scan_run_id=run_id, source=connector.name, payload=payload))
            records = persist_batch(session, normalized, today)
            session.commit()
        if raw.errors:
            status = "partial" if raw.payloads else "failed"
            error = "\n".join(raw.errors)[:MAX_ERROR_LEN]
    except Exception as exc:  # isolate one connector's failure from the rest
        logger.exception("Connector %s failed", connector.name)
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:MAX_ERROR_LEN]

    with session_factory() as session:
        run = session.get(ScanRun, run_id)
        run.status = status
        run.records = records
        run.error = error
        run.finished_at = utcnow()
        session.commit()
    return run_id


def purge_raw_payloads(session: Session, older_than: datetime) -> int:
    result = session.execute(delete(RawPayload).where(RawPayload.fetched_at < older_than))
    return result.rowcount or 0
```

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_scan.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/scan.py backend/app/connectors/registry.py backend/tests/test_scan.py
git commit -m "feat(pipeline): add isolated scan runner and connector registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Velocity + hot flags

**Files:**
- Create: `backend/app/analysis/velocity.py`
- Test: `backend/tests/test_velocity.py`

**Interfaces:**
- Produces:
  - `SnapshotPoint(date: date, reviews: int | None, favorites: int | None)` (frozen dataclass)
  - `compute_velocity(snapshots: list[SnapshotPoint], listed_on: date | None) -> tuple[float | None, float | None]` → `(delta_7d, velocity)`
  - `hot_ids(rows: Iterable[tuple[int, tuple[str, str], float | None]], top_fraction: float = 0.10) -> set[int]`
  - constant `MIN_SPAN_DAYS = 3`

Quy tắc: metric = `reviews` nếu có, ngược lại `favorites`. Snapshot mới nhất L; baseline B = snapshot gần nhất có `date <= L.date - 7`, nếu không có thì snapshot sớm nhất. `span = (L.date - B.date).days`; span < 3 → `(None, None)`. `delta_7d = (m(L) - m(B)) * 7 / span`. `weeks = (L.date - listed_on).days / 7` (listed_on None → 1). `velocity = delta_7d / max(1, weeks)`.

- [ ] **Step 1: Write the failing test `backend/tests/test_velocity.py`**

```python
from datetime import date

import pytest

from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids


def fav(d: date, n: int) -> SnapshotPoint:
    return SnapshotPoint(date=d, reviews=None, favorites=n)


def test_needs_two_snapshots():
    assert compute_velocity([fav(date(2026, 9, 27), 10)], None) == (None, None)


def test_needs_three_day_span():
    points = [fav(date(2026, 9, 25), 10), fav(date(2026, 9, 27), 20)]
    assert compute_velocity(points, None) == (None, None)


def test_weekly_delta_divided_by_weeks_since_listed():
    points = [fav(date(2026, 9, 20), 100), fav(date(2026, 9, 27), 170)]
    delta, velocity = compute_velocity(points, date(2026, 9, 13))
    assert delta == pytest.approx(70)
    assert velocity == pytest.approx(35)  # 2 weeks old


def test_baseline_is_closest_snapshot_seven_days_back():
    points = [
        fav(date(2026, 9, 17), 50),
        fav(date(2026, 9, 20), 100),
        fav(date(2026, 9, 24), 130),
        fav(date(2026, 9, 27), 170),
    ]
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(70)


def test_short_span_is_scaled_to_seven_days():
    points = [fav(date(2026, 9, 24), 130), fav(date(2026, 9, 27), 160)]
    delta, velocity = compute_velocity(points, None)
    assert delta == pytest.approx(70)
    assert velocity == pytest.approx(70)


def test_reviews_preferred_over_favorites():
    points = [
        SnapshotPoint(date(2026, 9, 20), reviews=10, favorites=999),
        SnapshotPoint(date(2026, 9, 27), reviews=24, favorites=0),
    ]
    delta, _ = compute_velocity(points, None)
    assert delta == pytest.approx(14)


def test_recent_listing_is_not_boosted_above_delta():
    points = [fav(date(2026, 9, 20), 0), fav(date(2026, 9, 27), 50)]
    _, velocity = compute_velocity(points, date(2026, 9, 25))
    assert velocity == pytest.approx(50)


def test_hot_ids_top_ten_percent_per_group():
    rows = [(i, ("etsy", "tshirt"), float(i)) for i in range(1, 21)]
    rows += [(100, ("etsy", "hoodie"), 5.0), (101, ("etsy", "hoodie"), None), (102, ("etsy", "hoodie"), -1.0)]
    assert hot_ids(rows) == {20, 19, 100}


def test_hot_ids_ignores_non_positive():
    assert hot_ids([(1, ("etsy", "tshirt"), 0.0), (2, ("etsy", "tshirt"), None)]) == set()
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_velocity.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.analysis.velocity'`

- [ ] **Step 3: Create `backend/app/analysis/velocity.py`**

```python
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

MIN_SPAN_DAYS = 3
WINDOW_DAYS = 7


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    reviews: int | None
    favorites: int | None


def _metric(point: SnapshotPoint) -> int | None:
    return point.reviews if point.reviews is not None else point.favorites


def compute_velocity(
    snapshots: list[SnapshotPoint], listed_on: date | None
) -> tuple[float | None, float | None]:
    """Return (delta over 7 days, delta per week of listing age)."""
    points = sorted((p for p in snapshots if _metric(p) is not None), key=lambda p: p.date)
    if len(points) < 2:
        return None, None
    latest = points[-1]
    cutoff = latest.date - timedelta(days=WINDOW_DAYS)
    older = [p for p in points[:-1] if p.date <= cutoff]
    base = older[-1] if older else points[0]
    span = (latest.date - base.date).days
    if span < MIN_SPAN_DAYS:
        return None, None
    delta_7d = (_metric(latest) - _metric(base)) * WINDOW_DAYS / span
    weeks = (latest.date - listed_on).days / 7 if listed_on else 1.0
    return delta_7d, delta_7d / max(1.0, weeks)


def hot_ids(
    rows: Iterable[tuple[int, tuple[str, str], float | None]], top_fraction: float = 0.10
) -> set[int]:
    """Top `top_fraction` of positive velocities within each (source, product_type) group."""
    groups: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)
    for product_id, group, velocity in rows:
        if velocity is not None and velocity > 0:
            groups[group].append((velocity, product_id))
    hot: set[int] = set()
    for values in groups.values():
        values.sort(reverse=True)
        n = max(1, math.ceil(len(values) * top_fraction))
        hot.update(pid for _, pid in values[:n])
    return hot
```

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_velocity.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/analysis/velocity.py backend/tests/test_velocity.py
git commit -m "feat(analysis): add product velocity and hot detection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Products API

**Files:**
- Create: `backend/app/api/__init__.py` (empty), `backend/app/api/deps.py`, `backend/app/api/schemas.py`, `backend/app/api/products.py`
- Modify: `backend/app/main.py` (include router)
- Test: `backend/tests/test_api_products.py`

**Interfaces:**
- Consumes: models, `SnapshotPoint`, `compute_velocity`, `hot_ids` (Task 7)
- Produces: `get_session(request) -> Iterator[Session]`; schemas `ProductOut`, `ProductPage` (others added in Tasks 9–10); `GET /api/products?source=&type=&keyword_id=&sort=velocity|reviews|price|newest&limit=60&offset=0` → `{"total": int, "items": [ProductOut]}`.

`ProductOut` fields: `id, source, title, url, image_url, shop_name, price, currency, product_type, listed_at, reviews, favorites, rating, delta_7d, velocity, hot, keywords: list[str]` (reviews/favorites/rating từ snapshot mới nhất).

Ghi chú: Phase 1 tính velocity cho toàn bộ sản phẩm mỗi request (đủ nhanh với vài nghìn sản phẩm); hot luôn tính trên toàn bộ nhóm, không phụ thuộc bộ lọc.

- [ ] **Step 1: Write the failing test `backend/tests/test_api_products.py`**

```python
from datetime import date, datetime

import pytest

from app.keywords import get_or_create_keyword
from app.models import Product, ProductKeyword, ProductSnapshot


def add_product(session, external_id, product_type, listed_at, snapshots, keyword=None, price=20.0):
    p = Product(
        source="etsy",
        external_id=external_id,
        title=f"Product {external_id}",
        url=f"https://etsy.com/{external_id}",
        product_type=product_type,
        listed_at=listed_at,
        price=price,
        currency="USD",
    )
    session.add(p)
    session.flush()
    for d, fav in snapshots:
        session.add(ProductSnapshot(product_id=p.id, date=d, favorites=fav))
    if keyword:
        kw = get_or_create_keyword(session, keyword)
        session.add(ProductKeyword(product_id=p.id, keyword_id=kw.id, rank=1, last_seen=snapshots[-1][0]))
    return p


@pytest.fixture
def catalog(session):
    a = add_product(
        session, "A", "tshirt", datetime(2026, 9, 13),
        [(date(2026, 9, 20), 100), (date(2026, 9, 27), 170)], keyword="nurse", price=25.0,
    )
    b = add_product(
        session, "B", "tshirt", datetime(2025, 1, 1),
        [(date(2026, 9, 20), 500), (date(2026, 9, 27), 510)], price=15.0,
    )
    c = add_product(session, "C", "hoodie", datetime(2026, 9, 26), [(date(2026, 9, 27), 3)], price=40.0)
    session.commit()
    return {"A": a.id, "B": b.id, "C": c.id}


def ids(resp):
    return [item["id"] for item in resp.json()["items"]]


def test_default_sort_is_velocity_with_hot_flag(client, catalog):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert ids(resp) == [catalog["A"], catalog["B"], catalog["C"]]
    a, b, c = body["items"]
    assert a["hot"] is True and b["hot"] is False and c["hot"] is False
    assert a["delta_7d"] == pytest.approx(70)
    assert a["velocity"] == pytest.approx(35)
    assert a["favorites"] == 170
    assert a["keywords"] == ["nurse"]
    assert c["velocity"] is None


def test_sort_by_reviews_and_price(client, catalog):
    assert ids(client.get("/api/products?sort=reviews")) == [catalog["B"], catalog["A"], catalog["C"]]
    assert ids(client.get("/api/products?sort=price")) == [catalog["B"], catalog["A"], catalog["C"]]
    assert ids(client.get("/api/products?sort=newest")) == [catalog["C"], catalog["A"], catalog["B"]]


def test_filters(client, catalog, session):
    assert ids(client.get("/api/products?type=hoodie")) == [catalog["C"]]
    assert ids(client.get("/api/products?source=amazon")) == []
    kw_id = get_or_create_keyword(session, "nurse").id
    assert ids(client.get(f"/api/products?keyword_id={kw_id}")) == [catalog["A"]]


def test_pagination(client, catalog):
    resp = client.get("/api/products?limit=1&offset=1")
    assert resp.json()["total"] == 3
    assert ids(resp) == [catalog["B"]]


def test_invalid_sort_rejected(client):
    assert client.get("/api/products?sort=bogus").status_code == 422
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_api_products.py -v`
Expected: FAIL — 404 on `/api/products`

- [ ] **Step 3: Create `backend/app/api/deps.py`**

```python
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
```

- [ ] **Step 4: Create `backend/app/api/schemas.py`**

```python
from datetime import datetime

from pydantic import BaseModel


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
    delta_7d: float | None
    velocity: float | None
    hot: bool
    keywords: list[str]


class ProductPage(BaseModel):
    total: int
    items: list[ProductOut]
```

- [ ] **Step 5: Create `backend/app/api/products.py`**

```python
from collections import defaultdict
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.analysis.velocity import SnapshotPoint, compute_velocity, hot_ids
from app.api.deps import get_session
from app.api.schemas import ProductOut, ProductPage
from app.models import Keyword, Product, ProductKeyword

router = APIRouter(prefix="/api")

SortKey = Literal["velocity", "reviews", "price", "newest"]


def _desc_none_last(value: float | None) -> tuple[bool, float]:
    return (value is None, -(value or 0))


SORTS: dict[str, Callable[[ProductOut], Any]] = {
    "velocity": lambda p: _desc_none_last(p.velocity),
    "reviews": lambda p: _desc_none_last(p.reviews if p.reviews is not None else p.favorites),
    "price": lambda p: (p.price is None, p.price or 0),
    "newest": lambda p: _desc_none_last(p.listed_at.timestamp() if p.listed_at else None),
}


@router.get("/products", response_model=ProductPage)
def list_products(
    source: str | None = None,
    product_type: str | None = Query(None, alias="type"),
    keyword_id: int | None = None,
    sort: SortKey = "velocity",
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> ProductPage:
    products = session.scalars(select(Product).options(selectinload(Product.snapshots))).all()

    metrics = {
        p.id: compute_velocity(
            [SnapshotPoint(s.date, s.reviews, s.favorites) for s in p.snapshots],
            p.listed_at.date() if p.listed_at else None,
        )
        for p in products
    }
    hot = hot_ids((p.id, (p.source, p.product_type), metrics[p.id][1]) for p in products)

    keyword_texts: dict[int, list[str]] = defaultdict(list)
    keyword_ids: dict[int, set[int]] = defaultdict(set)
    rows = session.execute(
        select(ProductKeyword.product_id, Keyword.id, Keyword.text).join(
            Keyword, Keyword.id == ProductKeyword.keyword_id
        )
    )
    for product_id, kid, text in rows:
        keyword_texts[product_id].append(text)
        keyword_ids[product_id].add(kid)

    items = [
        _to_out(p, metrics[p.id], p.id in hot, sorted(keyword_texts[p.id]))
        for p in products
        if (source is None or p.source == source)
        and (product_type is None or p.product_type == product_type)
        and (keyword_id is None or keyword_id in keyword_ids[p.id])
    ]
    items.sort(key=SORTS[sort])
    return ProductPage(total=len(items), items=items[offset : offset + limit])


def _to_out(
    p: Product, metric: tuple[float | None, float | None], hot: bool, keywords: list[str]
) -> ProductOut:
    latest = p.snapshots[-1] if p.snapshots else None
    return ProductOut(
        id=p.id,
        source=p.source,
        title=p.title,
        url=p.url,
        image_url=p.image_url,
        shop_name=p.shop_name,
        price=p.price,
        currency=p.currency,
        product_type=p.product_type,
        listed_at=p.listed_at,
        reviews=latest.reviews if latest else None,
        favorites=latest.favorites if latest else None,
        rating=latest.rating if latest else None,
        delta_7d=metric[0],
        velocity=metric[1],
        hot=hot,
        keywords=keywords,
    )
```

- [ ] **Step 6: Include the router in `backend/app/main.py`** — add import `from app.api import products` and, right before `return app`:

```python
    app.include_router(products.router)
```

- [ ] **Step 7: Run tests**

Run: `cd backend && .venv/bin/pytest tests/test_api_products.py -v`
Expected: 5 passed

- [ ] **Step 8: Commit**

```bash
git add backend/app/api backend/app/main.py backend/tests/test_api_products.py
git commit -m "feat(api): add best sellers products endpoint with velocity and hot flags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Seeds + Settings API

**Files:**
- Create: `backend/app/settings_store.py`, `backend/app/api/seeds.py`, `backend/app/api/settings.py`
- Modify: `backend/app/api/schemas.py` (append schemas), `backend/app/main.py` (connector_factory param + routers)
- Test: `backend/tests/test_api_seeds_settings.py`

**Interfaces:**
- Consumes: `get_or_create_keyword`, `normalize_keyword` (Task 2); `connector_status`, `build_connectors`, `ConnectorFactory` (Task 6); `get_session` (Task 8)
- Produces:
  - `DEFAULTS = {"scan_hour_utc": 11, "connectors_enabled": {}}`; `get_setting(session, key)`, `set_setting(session, key, value)` (flush, không commit)
  - `GET /api/seeds` → `[SeedOut]`; `POST /api/seeds {"keyword"}` → 201 `SeedOut` | 409 duplicate | 422 blank; `DELETE /api/seeds/{id}` → 204 | 404
  - `GET /api/settings` → `SettingsOut {scan_hour_utc, connectors: [ConnectorStatusOut]}`; `PUT /api/settings {scan_hour_utc?, connectors_enabled?}` → `SettingsOut` (merge overrides; 400 unknown connector; 422 hour ngoài 0–23)
  - `create_app(..., connector_factory: ConnectorFactory = build_connectors)`; stored at `app.state.connector_factory`

- [ ] **Step 1: Write the failing test `backend/tests/test_api_seeds_settings.py`**

```python
def test_seed_crud(client):
    resp = client.post("/api/seeds", json={"keyword": "  Dog   Mom "})
    assert resp.status_code == 201
    seed = resp.json()
    assert seed["keyword"] == "dog mom"
    assert seed["active"] is True
    assert isinstance(seed["keyword_id"], int)

    assert client.post("/api/seeds", json={"keyword": "dog mom"}).status_code == 409
    assert client.post("/api/seeds", json={"keyword": "   "}).status_code == 422

    assert [s["keyword"] for s in client.get("/api/seeds").json()] == ["dog mom"]
    assert client.delete(f"/api/seeds/{seed['id']}").status_code == 204
    assert client.delete(f"/api/seeds/{seed['id']}").status_code == 404
    assert client.get("/api/seeds").json() == []


def test_settings_defaults(client):
    body = client.get("/api/settings").json()
    assert body == {
        "scan_hour_utc": 11,
        "connectors": [{"name": "etsy", "kind": "product", "configured": True, "enabled": True}],
    }


def test_settings_update_merges_and_validates(client):
    body = client.put("/api/settings", json={"connectors_enabled": {"etsy": False}}).json()
    assert body["connectors"][0]["enabled"] is False

    body = client.put("/api/settings", json={"scan_hour_utc": 3}).json()
    assert body["scan_hour_utc"] == 3
    assert body["connectors"][0]["enabled"] is False  # untouched

    assert client.put("/api/settings", json={"scan_hour_utc": 24}).status_code == 422
    assert client.put("/api/settings", json={"connectors_enabled": {"nope": True}}).status_code == 400


def test_settings_never_exposes_api_key(client):
    assert "test-key" not in client.get("/api/settings").text
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/pytest tests/test_api_seeds_settings.py -v`
Expected: FAIL — 404 / 405 on `/api/seeds`

- [ ] **Step 3: Create `backend/app/settings_store.py`**

```python
import copy
from typing import Any

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULTS: dict[str, Any] = {
    "scan_hour_utc": 11,  # 11:00 UTC = 7:00 ET = 18:00 giờ Việt Nam
    "connectors_enabled": {},  # name -> bool; missing means enabled
}


def get_setting(session: Session, key: str) -> Any:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(Setting, key)
    return copy.deepcopy(row.value if row is not None else DEFAULTS[key])


def set_setting(session: Session, key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = session.get(Setting, key)
    if row is None:
        session.add(Setting(key=key, value=value))
    else:
        row.value = value
    session.flush()
```

- [ ] **Step 4: Append to `backend/app/api/schemas.py`** — add `ConfigDict, Field, field_validator` to the pydantic import, then append:

```python
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
```

(`ConfigDict` is used in Task 10; importing it now is fine.)

- [ ] **Step 5: Create `backend/app/api/seeds.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import SeedIn, SeedOut
from app.keywords import get_or_create_keyword, normalize_keyword
from app.models import Seed

router = APIRouter(prefix="/api")


def _to_out(session: Session, seed: Seed) -> SeedOut:
    keyword = get_or_create_keyword(session, seed.keyword)
    return SeedOut(
        id=seed.id,
        keyword=seed.keyword,
        active=seed.active,
        created_at=seed.created_at,
        keyword_id=keyword.id,
    )


@router.get("/seeds", response_model=list[SeedOut])
def list_seeds(session: Session = Depends(get_session)) -> list[SeedOut]:
    seeds = session.scalars(select(Seed).order_by(Seed.id)).all()
    out = [_to_out(session, s) for s in seeds]
    session.commit()  # persists keywords created for legacy seeds
    return out


@router.post("/seeds", response_model=SeedOut, status_code=201)
def create_seed(body: SeedIn, session: Session = Depends(get_session)) -> SeedOut:
    text = normalize_keyword(body.keyword)
    if session.scalar(select(Seed).where(Seed.keyword == text)) is not None:
        raise HTTPException(status_code=409, detail="Seed already exists")
    seed = Seed(keyword=text)
    session.add(seed)
    session.flush()
    out = _to_out(session, seed)
    session.commit()
    return out


@router.delete("/seeds/{seed_id}", status_code=204)
def delete_seed(seed_id: int, session: Session = Depends(get_session)) -> Response:
    seed = session.get(Seed, seed_id)
    if seed is None:
        raise HTTPException(status_code=404, detail="Seed not found")
    session.delete(seed)
    session.commit()
    return Response(status_code=204)
```

- [ ] **Step 6: Create `backend/app/api/settings.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ConnectorStatusOut, SettingsIn, SettingsOut
from app.connectors.registry import connector_status
from app.settings_store import get_setting, set_setting

router = APIRouter(prefix="/api")


def settings_out(request: Request, session: Session) -> SettingsOut:
    overrides = get_setting(session, "connectors_enabled")
    return SettingsOut(
        scan_hour_utc=get_setting(session, "scan_hour_utc"),
        connectors=[
            ConnectorStatusOut(**c) for c in connector_status(request.app.state.settings, overrides)
        ],
    )


@router.get("/settings", response_model=SettingsOut)
def read_settings(request: Request, session: Session = Depends(get_session)) -> SettingsOut:
    return settings_out(request, session)


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    body: SettingsIn, request: Request, session: Session = Depends(get_session)
) -> SettingsOut:
    if body.connectors_enabled is not None:
        known = {c["name"] for c in connector_status(request.app.state.settings, {})}
        unknown = sorted(set(body.connectors_enabled) - known)
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown connectors: {unknown}")
        merged = {**get_setting(session, "connectors_enabled"), **body.connectors_enabled}
        set_setting(session, "connectors_enabled", merged)
    if body.scan_hour_utc is not None:
        set_setting(session, "scan_hour_utc", body.scan_hour_utc)
    session.commit()
    return settings_out(request, session)
```

- [ ] **Step 7: Update `backend/app/main.py`** — replace the whole file:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.api import products, seeds
from app.api import settings as settings_api
from app.config import Settings, get_settings
from app.connectors.registry import ConnectorFactory, build_connectors
from app.db import make_engine, make_session_factory


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    connector_factory: ConnectorFactory = build_connectors,
) -> FastAPI:
    settings = settings or get_settings()
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.database_url))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="POD Trend Radar", lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.connector_factory = connector_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    for module in (products, seeds, settings_api):
        app.include_router(module.router)
    return app
```

- [ ] **Step 8: Run all backend tests**

Run: `cd backend && .venv/bin/pytest -v`
Expected: all passed

- [ ] **Step 9: Commit**

```bash
git add backend/app backend/tests/test_api_seeds_settings.py
git commit -m "feat(api): add seeds watchlist and settings endpoints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Scheduler + Scans + Health API

**Files:**
- Create: `backend/app/services/__init__.py` (empty), `backend/app/services/scans.py`, `backend/app/scheduler.py`, `backend/app/api/scans.py`, `backend/app/api/health.py`
- Modify: `backend/app/api/schemas.py` (append), `backend/app/api/settings.py` (reschedule), `backend/app/main.py` (lifespan + routers)
- Test: `backend/tests/test_scheduler.py`, `backend/tests/test_api_scans_health.py`

**Interfaces:**
- Consumes: `run_scan` (Task 6), `get_setting` (Task 9), `connector_status` (Task 6), `app.state.connector_factory` (Task 9)
- Produces:
  - `scan_in_progress(session) -> bool` (có ScanRun `running` bắt đầu trong 1 giờ qua)
  - `resolve_connectors(app, session, only: list[str] | None = None) -> list[Connector]`
  - `async execute_scan(app, connectors) -> list[int]`
  - `JOB_ID = "daily_scan"`, `start_scheduler(app) -> AsyncIOScheduler` (sets `app.state.scheduler`), `reschedule(app, hour: int) -> None`, `async scheduled_scan(app) -> None`
  - `POST /api/scans {"sources"?: [str]}` → 202 `{"sources": [names]}` | 409 running | 400 none enabled; `GET /api/scans?limit=20` → `[ScanRunOut]`; `GET /api/health/sources` → `[SourceHealthOut]`

- [ ] **Step 1: Write the failing test `backend/tests/test_scheduler.py`**

```python
from types import SimpleNamespace

from app.scheduler import JOB_ID, reschedule, start_scheduler
from app.settings_store import set_setting


async def test_scheduler_uses_stored_hour_and_reschedules(session_factory):
    with session_factory() as s:
        set_setting(s, "scan_hour_utc", 5)
        s.commit()
    app = SimpleNamespace(state=SimpleNamespace(session_factory=session_factory))

    scheduler = start_scheduler(app)
    try:
        assert app.state.scheduler is scheduler
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 5
        reschedule(app, 3)
        assert scheduler.get_job(JOB_ID).next_run_time.hour == 3
    finally:
        scheduler.shutdown(wait=False)


def test_reschedule_without_scheduler_is_noop():
    reschedule(SimpleNamespace(state=SimpleNamespace()), 3)
```

- [ ] **Step 2: Write the failing test `backend/tests/test_api_scans_health.py`**

```python
from app.db import utcnow
from app.models import ScanRun
from tests.fakes import FakeConnector


def test_start_scan_runs_in_background(make_client, session):
    fake = FakeConnector()
    client = make_client(connector_factory=lambda settings, overrides, only: [fake])

    resp = client.post("/api/scans", json={})
    assert resp.status_code == 202
    assert resp.json() == {"sources": ["fake"]}

    runs = client.get("/api/scans").json()
    assert len(runs) == 1
    assert runs[0]["source"] == "fake"
    assert runs[0]["status"] == "ok"
    assert runs[0]["records"] == 1


def test_start_scan_passes_requested_sources(make_client):
    seen = {}

    def factory(settings, overrides, only):
        seen["only"] = only
        return [FakeConnector()]

    client = make_client(connector_factory=factory)
    client.post("/api/scans", json={"sources": ["etsy"]})
    assert seen["only"] == ["etsy"]


def test_start_scan_conflicts_when_running(make_client, session):
    session.add(ScanRun(source="fake", status="running", started_at=utcnow()))
    session.commit()
    client = make_client(connector_factory=lambda s, o, only: [FakeConnector()])
    assert client.post("/api/scans", json={}).status_code == 409


def test_start_scan_requires_enabled_connector(make_client):
    client = make_client(connector_factory=lambda s, o, only: [])
    assert client.post("/api/scans", json={}).status_code == 400


def test_source_health_reports_last_finished_run(client, session):
    session.add(ScanRun(source="etsy", status="ok", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="failed", error="HTTP 403", finished_at=utcnow()))
    session.add(ScanRun(source="etsy", status="running"))
    session.commit()

    [etsy] = client.get("/api/health/sources").json()
    assert etsy["name"] == "etsy"
    assert etsy["configured"] is True
    assert etsy["last_status"] == "failed"
    assert etsy["last_error"] == "HTTP 403"
    assert etsy["last_finished_at"] is not None
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_scheduler.py tests/test_api_scans_health.py -v`
Expected: ERROR — `ModuleNotFoundError: No module named 'app.scheduler'`

- [ ] **Step 4: Create `backend/app/services/scans.py`**

```python
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import Connector
from app.db import utcnow
from app.models import ScanRun
from app.pipeline.scan import run_scan
from app.settings_store import get_setting

RUNNING_STALE_AFTER = timedelta(hours=1)


def scan_in_progress(session: Session) -> bool:
    cutoff = utcnow() - RUNNING_STALE_AFTER
    running = session.scalar(
        select(func.count())
        .select_from(ScanRun)
        .where(ScanRun.status == "running", ScanRun.started_at >= cutoff)
    )
    return bool(running)


def resolve_connectors(app: Any, session: Session, only: list[str] | None = None) -> list[Connector]:
    overrides = get_setting(session, "connectors_enabled")
    return app.state.connector_factory(app.state.settings, overrides, only)


async def execute_scan(app: Any, connectors: list[Connector]) -> list[int]:
    return await run_scan(
        app.state.session_factory,
        connectors,
        retention_days=app.state.settings.raw_retention_days,
    )
```

- [ ] **Step 5: Create `backend/app/scheduler.py`**

```python
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.scans import execute_scan, resolve_connectors, scan_in_progress
from app.settings_store import get_setting

logger = logging.getLogger(__name__)
JOB_ID = "daily_scan"


def _trigger(hour: int) -> CronTrigger:
    return CronTrigger(hour=hour, minute=0, timezone="UTC")


async def scheduled_scan(app: Any) -> None:
    with app.state.session_factory() as session:
        if scan_in_progress(session):
            logger.info("Skipping scheduled scan: another scan is running")
            return
        connectors = resolve_connectors(app, session)
    if connectors:
        await execute_scan(app, connectors)


def start_scheduler(app: Any) -> AsyncIOScheduler:
    with app.state.session_factory() as session:
        hour = get_setting(session, "scan_hour_utc")
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_scan,
        _trigger(hour),
        id=JOB_ID,
        args=[app],
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler


def reschedule(app: Any, hour: int) -> None:
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler is not None:
        scheduler.reschedule_job(JOB_ID, trigger=_trigger(hour))
```

- [ ] **Step 6: Append to `backend/app/api/schemas.py`**

```python
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
```

- [ ] **Step 7: Create `backend/app/api/scans.py`**

```python
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import ScanIn, ScanRunOut, ScanStarted
from app.models import ScanRun
from app.services.scans import execute_scan, resolve_connectors, scan_in_progress

router = APIRouter(prefix="/api")


@router.post("/scans", response_model=ScanStarted, status_code=202)
def start_scan(
    background: BackgroundTasks,
    request: Request,
    body: ScanIn | None = None,
    session: Session = Depends(get_session),
) -> ScanStarted:
    if scan_in_progress(session):
        raise HTTPException(status_code=409, detail="A scan is already running")
    connectors = resolve_connectors(request.app, session, body.sources if body else None)
    if not connectors:
        raise HTTPException(status_code=400, detail="No enabled and configured connectors")
    background.add_task(execute_scan, request.app, connectors)
    return ScanStarted(sources=[c.name for c in connectors])


@router.get("/scans", response_model=list[ScanRunOut])
def list_scans(
    limit: int = Query(20, ge=1, le=200), session: Session = Depends(get_session)
) -> list[ScanRun]:
    return list(session.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit)))
```

- [ ] **Step 8: Create `backend/app/api/health.py`**

```python
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.schemas import SourceHealthOut
from app.connectors.registry import connector_status
from app.models import ScanRun
from app.settings_store import get_setting

router = APIRouter(prefix="/api")


@router.get("/health/sources", response_model=list[SourceHealthOut])
def sources_health(request: Request, session: Session = Depends(get_session)) -> list[SourceHealthOut]:
    overrides = get_setting(session, "connectors_enabled")
    out = []
    for status in connector_status(request.app.state.settings, overrides):
        last = session.scalar(
            select(ScanRun)
            .where(ScanRun.source == status["name"], ScanRun.status != "running")
            .order_by(ScanRun.id.desc())
            .limit(1)
        )
        out.append(
            SourceHealthOut(
                **status,
                last_status=last.status if last else None,
                last_finished_at=last.finished_at if last else None,
                last_error=last.error if last else None,
            )
        )
    return out
```

- [ ] **Step 9: Reschedule on hour change in `backend/app/api/settings.py`** — add import `from app.scheduler import reschedule` and replace the `scan_hour_utc` block in `update_settings` with:

```python
    if body.scan_hour_utc is not None:
        set_setting(session, "scan_hour_utc", body.scan_hour_utc)
    session.commit()
    if body.scan_hour_utc is not None:
        reschedule(request.app, body.scan_hour_utc)
    return settings_out(request, session)
```

(Remove the old `session.commit()` / `return` lines so commit happens once.)

- [ ] **Step 10: Update `backend/app/main.py`** — change the api import line to:

```python
from app.api import health, products, scans, seeds
```

add `from app.scheduler import start_scheduler`, replace the `lifespan` function with:

```python
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = start_scheduler(app) if settings.scheduler_enabled else None
        yield
        if scheduler is not None:
            scheduler.shutdown(wait=False)
```

and replace the router loop with:

```python
    for module in (products, seeds, settings_api, scans, health):
        app.include_router(module.router)
```

- [ ] **Step 11: Run all backend tests**

Run: `cd backend && .venv/bin/pytest -v`
Expected: all passed

- [ ] **Step 12: Commit**

```bash
git add backend/app backend/tests/test_scheduler.py backend/tests/test_api_scans_health.py
git commit -m "feat(api): add daily scheduler, scan trigger/log and source health

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Live smoke script

**Files:**
- Create: `backend/scripts/smoke.py`

**Interfaces:**
- Consumes: `get_settings`, `make_all_connectors` (Task 6)
- Produces: `python scripts/smoke.py [keyword] [--save]` — gọi thật từng connector đã cấu hình, in thống kê, exit 1 nếu có connector lỗi; `--save` ghi payload đầu tiên vào `tests/fixtures/<source>/live_sample.json`.

- [ ] **Step 1: Create `backend/scripts/smoke.py`**

```python
"""Live check of every configured connector. Usage: python scripts/smoke.py [keyword] [--save]"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.connectors.registry import make_all_connectors

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("keyword", nargs="?", default="nurse")
    parser.add_argument("--save", action="store_true", help="save first raw payload as fixture")
    args = parser.parse_args()

    failed = False
    for connector in make_all_connectors(get_settings()):
        if not connector.enabled():
            print(f"[skip] {connector.name}: not configured")
            continue
        try:
            raw = await connector.fetch([args.keyword])
        except Exception as exc:
            print(f"[FAIL] {connector.name}: {type(exc).__name__}: {exc}")
            failed = True
            continue
        batch = connector.normalize(raw, date.today())
        with_image = sum(1 for p in batch.products if p.image_url)
        status = "FAIL" if raw.errors and not raw.payloads else "ok"
        failed = failed or status == "FAIL"
        print(
            f"[{status}] {connector.name}: {len(raw.payloads)} payloads, {len(raw.errors)} errors, "
            f"{len(batch.products)} products ({with_image} with image), {len(batch.signals)} signals"
        )
        for error in raw.errors[:3]:
            print(f"    error: {error}")
        for p in batch.products[:5]:
            print(
                f"    - [{p.product_type}] {p.title[:70]} | {p.price} {p.currency} "
                f"| fav={p.favorites} rev={p.reviews} | shop={p.shop_name}"
            )
        if args.save and raw.payloads:
            out = FIXTURES / connector.name / "live_sample.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(raw.payloads[0], indent=2))
            print(f"    saved {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Verify it runs without a key**

Run: `cd backend && ETSY_API_KEY= .venv/bin/python scripts/smoke.py`
Expected: `[skip] etsy: not configured`, exit code 0

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/smoke.py
git commit -m "feat(backend): add live connector smoke script

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Frontend scaffold, API client, layout

**Files:**
- Create (generated): `frontend/` via create-next-app
- Create: `frontend/.env.local.example`, `frontend/lib/api.ts`, `frontend/lib/format.ts`
- Modify (overwrite): `frontend/app/layout.tsx`, `frontend/app/globals.css`, `frontend/app/page.tsx`; root `Makefile`

**Interfaces:**
- Consumes: backend REST API (Tasks 8–10)
- Produces: `api` object (`listProducts, listSeeds, addSeed, deleteSeed, getSettings, updateSettings, startScan, listScans, sourceHealth`), `ApiError(status, message)`, types `Product, ProductPage, ProductQuery, ProductSort, Seed, ConnectorStatus, AppSettings, ScanRun, SourceHealth`; `parseUtc, timeAgo, formatPrice, PRODUCT_TYPE_LABEL` from `lib/format.ts`.

- [ ] **Step 1: Scaffold Next.js**

Run (from repo root):
```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --no-src-dir --import-alias "@/*" --use-npm --yes
```
Expected: `frontend/` created; `cd frontend && npm run build` succeeds on the default page. Delete the nested git repo if create-next-app made one: `rm -rf frontend/.git`.

- [ ] **Step 2: Create `frontend/.env.local.example`** and copy it to `.env.local`

```dotenv
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Run: `cp frontend/.env.local.example frontend/.env.local`

- [ ] **Step 3: Create `frontend/lib/api.ts`**

```ts
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export type ProductType = "tshirt" | "sweatshirt" | "hoodie";
export type ProductSort = "velocity" | "reviews" | "price" | "newest";

export type Product = {
  id: number;
  source: string;
  title: string;
  url: string;
  image_url: string | null;
  shop_name: string | null;
  price: number | null;
  currency: string | null;
  product_type: ProductType;
  listed_at: string | null;
  reviews: number | null;
  favorites: number | null;
  rating: number | null;
  delta_7d: number | null;
  velocity: number | null;
  hot: boolean;
  keywords: string[];
};

export type ProductPage = { total: number; items: Product[] };

export type ProductQuery = {
  source?: string;
  type?: ProductType;
  keyword_id?: number;
  sort?: ProductSort;
  limit?: number;
  offset?: number;
};

export type Seed = { id: number; keyword: string; active: boolean; created_at: string; keyword_id: number };

export type ConnectorStatus = { name: string; kind: string; configured: boolean; enabled: boolean };

export type AppSettings = { scan_hour_utc: number; connectors: ConnectorStatus[] };

export type ScanStatus = "running" | "ok" | "partial" | "failed";

export type ScanRun = {
  id: number;
  source: string;
  status: ScanStatus;
  started_at: string;
  finished_at: string | null;
  records: number;
  error: string | null;
};

export type SourceHealth = ConnectorStatus & {
  last_status: ScanStatus | null;
  last_finished_at: string | null;
  last_error: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function toQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  listProducts: (q: ProductQuery = {}) => request<ProductPage>(`/api/products${toQuery(q)}`),
  listSeeds: () => request<Seed[]>("/api/seeds"),
  addSeed: (keyword: string) =>
    request<Seed>("/api/seeds", { method: "POST", body: JSON.stringify({ keyword }) }),
  deleteSeed: (id: number) => request<void>(`/api/seeds/${id}`, { method: "DELETE" }),
  getSettings: () => request<AppSettings>("/api/settings"),
  updateSettings: (body: { scan_hour_utc?: number; connectors_enabled?: Record<string, boolean> }) =>
    request<AppSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  startScan: (sources?: string[]) =>
    request<{ sources: string[] }>("/api/scans", { method: "POST", body: JSON.stringify({ sources }) }),
  listScans: (limit = 20) => request<ScanRun[]>(`/api/scans${toQuery({ limit })}`),
  sourceHealth: () => request<SourceHealth[]>("/api/health/sources"),
};
```

- [ ] **Step 4: Create `frontend/lib/format.ts`**

```ts
import type { ProductType } from "./api";

export const PRODUCT_TYPE_LABEL: Record<ProductType, string> = {
  tshirt: "T-shirt",
  sweatshirt: "Sweatshirt",
  hoodie: "Hoodie",
};

/** Backend returns naive UTC timestamps; mark them as UTC before parsing. */
export function parseUtc(iso: string): Date {
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const minutes = Math.floor((Date.now() - parseUtc(iso).getTime()) / 60000);
  if (minutes < 60) return `${Math.max(minutes, 0)} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} ngày trước`;
  if (days < 30) return `${Math.floor(days / 7)} tuần trước`;
  if (days < 365) return `${Math.floor(days / 30)} tháng trước`;
  return `${Math.floor(days / 365)} năm trước`;
}

export function formatPrice(price: number | null, currency: string | null): string {
  if (price === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: currency ?? "USD" }).format(price);
}
```

- [ ] **Step 5: Overwrite `frontend/app/globals.css`**

```css
@import "tailwindcss";
```

- [ ] **Step 6: Overwrite `frontend/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "POD Trend Radar",
  description: "Nghiên cứu ngách và sản phẩm POD bán chạy tại Mỹ",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="min-h-screen bg-zinc-50 text-zinc-900 antialiased">
        <header className="border-b border-zinc-200 bg-white">
          <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 text-sm">
            <span className="font-semibold">POD Trend Radar</span>
            <Link href="/products" className="text-zinc-600 hover:text-zinc-900">
              Best Sellers
            </Link>
            <Link href="/settings" className="text-zinc-600 hover:text-zinc-900">
              Cài đặt
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 7: Overwrite `frontend/app/page.tsx`**

```tsx
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/products");
}
```

- [ ] **Step 8: Add frontend targets to root `Makefile`** — change `.PHONY` line to include `dev-frontend`, append `cd frontend && npm install` as a second line of `install`, and add:

```makefile
dev-frontend:
	cd frontend && npm run dev
```

- [ ] **Step 9: Verify lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no lint errors; build succeeds (`/` and `/_not-found` routes).

- [ ] **Step 10: Commit**

```bash
git add frontend Makefile
git commit -m "feat(frontend): scaffold Next.js app with API client and layout

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Best Sellers page

**Files:**
- Create: `frontend/components/ProductCard.tsx`, `frontend/components/SourceHealthBanner.tsx`, `frontend/app/products/page.tsx`

**Interfaces:**
- Consumes: `api`, types, `timeAgo`, `formatPrice`, `PRODUCT_TYPE_LABEL` (Task 12)
- Produces: route `/products`; `<ProductCard product={Product} />`; `<SourceHealthBanner />`

Lưu ý lint: chỉ gọi `setState` trong callback của promise (không gọi đồng bộ trong thân `useEffect`), để tương thích rule `react-hooks/set-state-in-effect` của eslint-config-next mới.

- [ ] **Step 1: Create `frontend/components/ProductCard.tsx`**

```tsx
import type { Product } from "@/lib/api";
import { PRODUCT_TYPE_LABEL, formatPrice, timeAgo } from "@/lib/format";

export default function ProductCard({ product }: { product: Product }) {
  const isReviews = product.reviews !== null;
  const count = isReviews ? product.reviews : product.favorites;
  const label = isReviews ? "reviews" : "favorites";
  const delta = product.delta_7d;

  return (
    <a
      href={product.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white hover:shadow-md"
    >
      <div className="relative aspect-square bg-zinc-100">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={product.image_url} alt={product.title} className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-zinc-400">Không có ảnh</div>
        )}
        {product.hot && (
          <span className="absolute left-2 top-2 rounded bg-orange-500 px-1.5 py-0.5 text-xs font-semibold text-white">
            🔥 Hot
          </span>
        )}
        <span className="absolute right-2 top-2 rounded bg-white/90 px-1.5 py-0.5 text-xs uppercase text-zinc-600">
          {product.source}
        </span>
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3 text-sm">
        <p className="line-clamp-2 font-medium group-hover:underline">{product.title}</p>
        <div className="flex items-center justify-between">
          <span className="font-semibold">{formatPrice(product.price, product.currency)}</span>
          <span className="text-xs text-zinc-500">{PRODUCT_TYPE_LABEL[product.product_type]}</span>
        </div>
        <p className="text-xs text-zinc-600">
          {count ?? "—"} {label}
          {delta !== null && (
            <span className={delta > 0 ? "ml-1 text-green-600" : "ml-1 text-zinc-400"}>
              ({delta > 0 ? "+" : ""}
              {Math.round(delta)} / 7 ngày)
            </span>
          )}
        </p>
        <p className="text-xs text-zinc-500">
          {product.shop_name ?? "—"} · đăng {timeAgo(product.listed_at)}
        </p>
        {product.keywords.length > 0 && (
          <div className="mt-auto flex flex-wrap gap-1 pt-1">
            {product.keywords.map((k) => (
              <span key={k} className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs text-zinc-600">
                {k}
              </span>
            ))}
          </div>
        )}
      </div>
    </a>
  );
}
```

- [ ] **Step 2: Create `frontend/components/SourceHealthBanner.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { api, type SourceHealth } from "@/lib/api";
import { timeAgo } from "@/lib/format";

export default function SourceHealthBanner() {
  const [sources, setSources] = useState<SourceHealth[]>([]);

  useEffect(() => {
    api.sourceHealth().then(setSources).catch(() => setSources([]));
  }, []);

  const warnings = sources.filter(
    (s) => s.enabled && (!s.configured || s.last_status === "failed" || s.last_status === "partial"),
  );
  if (warnings.length === 0) return null;

  return (
    <div className="mb-4 space-y-1 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
      {warnings.map((s) => (
        <p key={s.name}>
          ⚠ <b>{s.name}</b>:{" "}
          {!s.configured
            ? "chưa cấu hình API key"
            : s.last_status === "failed"
              ? `lỗi lần quét gần nhất (${timeAgo(s.last_finished_at)})`
              : `lần quét gần nhất chỉ thành công một phần (${timeAgo(s.last_finished_at)})`}
        </p>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/app/products/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import ProductCard from "@/components/ProductCard";
import SourceHealthBanner from "@/components/SourceHealthBanner";
import { api, type ProductPage, type ProductQuery, type ProductSort, type ProductType, type Seed } from "@/lib/api";

const PAGE_SIZE = 60;

const SORTS: { value: ProductSort; label: string }[] = [
  { value: "velocity", label: "Tăng trưởng 7 ngày" },
  { value: "reviews", label: "Tổng reviews/favorites" },
  { value: "newest", label: "Mới đăng" },
  { value: "price", label: "Giá thấp → cao" },
];

const TYPES: { value: ProductType | ""; label: string }[] = [
  { value: "", label: "Tất cả loại" },
  { value: "tshirt", label: "T-shirt" },
  { value: "sweatshirt", label: "Sweatshirt" },
  { value: "hoodie", label: "Hoodie" },
];

type Result = { key: string; data?: ProductPage; error?: string };

const selectClass = "rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm";

export default function ProductsPage() {
  const [query, setQuery] = useState<ProductQuery>({ sort: "velocity", limit: PAGE_SIZE, offset: 0 });
  const [result, setResult] = useState<Result | null>(null);
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const key = JSON.stringify(query);
  const loading = result?.key !== key;

  useEffect(() => {
    api.listSeeds().then(setSeeds).catch(() => setSeeds([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .listProducts(query)
      .then((data) => !cancelled && setResult({ key, data }))
      .catch((err) => !cancelled && setResult({ key, error: String(err) }));
    return () => {
      cancelled = true;
    };
  }, [key, query]);

  const update = (patch: Partial<ProductQuery>) => setQuery((q) => ({ ...q, offset: 0, ...patch }));
  const offset = query.offset ?? 0;
  const total = result?.data?.total ?? 0;

  return (
    <div>
      <SourceHealthBanner />
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <h1 className="mr-auto text-xl font-semibold">Best Sellers</h1>
        <select className={selectClass} value={query.source ?? ""} onChange={(e) => update({ source: e.target.value || undefined })}>
          <option value="">Tất cả nguồn</option>
          <option value="etsy">Etsy</option>
        </select>
        <select
          className={selectClass}
          value={query.type ?? ""}
          onChange={(e) => update({ type: (e.target.value || undefined) as ProductType | undefined })}
        >
          {TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        <select
          className={selectClass}
          value={query.keyword_id ?? ""}
          onChange={(e) => update({ keyword_id: e.target.value ? Number(e.target.value) : undefined })}
        >
          <option value="">Tất cả keyword</option>
          {seeds.map((s) => (
            <option key={s.id} value={s.keyword_id}>
              {s.keyword}
            </option>
          ))}
        </select>
        <select className={selectClass} value={query.sort} onChange={(e) => update({ sort: e.target.value as ProductSort })}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
      <p className="mb-4 text-xs text-zinc-500">
        Reviews/favorites và mức tăng 7 ngày là chỉ số ước tính (proxy), không phải doanh số thật. 🔥 = top 10% tăng
        trưởng trong cùng nguồn và loại áo.
      </p>

      {result?.error && !loading && <p className="text-sm text-red-600">Không tải được dữ liệu: {result.error}</p>}
      {loading && <p className="text-sm text-zinc-500">Đang tải…</p>}
      {!loading && result?.data && result.data.items.length === 0 && (
        <p className="text-sm text-zinc-500">
          Chưa có sản phẩm. Thêm keyword trong <a href="/settings" className="underline">Cài đặt</a> rồi bấm “Quét ngay”.
        </p>
      )}

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {result?.data?.items.map((p) => <ProductCard key={p.id} product={p} />)}
      </div>

      {total > PAGE_SIZE && (
        <div className="mt-6 flex items-center justify-center gap-4 text-sm">
          <button
            className="rounded border px-3 py-1 disabled:opacity-40"
            disabled={offset === 0}
            onClick={() => setQuery((q) => ({ ...q, offset: Math.max(0, offset - PAGE_SIZE) }))}
          >
            ← Trước
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} / {total}
          </span>
          <button
            className="rounded border px-3 py-1 disabled:opacity-40"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setQuery((q) => ({ ...q, offset: offset + PAGE_SIZE }))}
          >
            Sau →
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Verify lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no errors; build lists route `/products`. If lint reports `@next/next/no-html-link-for-pages` on the `/settings` anchor, replace that `<a>` with `<Link href="/settings">` (import `Link` from `next/link`).

- [ ] **Step 5: Commit**

```bash
git add frontend/components frontend/app/products
git commit -m "feat(frontend): add Best Sellers page with filters, sorting and hot badges

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Settings page

**Files:**
- Create: `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `api`, `ApiError`, types, `timeAgo`, `parseUtc` (Task 12)
- Produces: route `/settings` — watchlist seeds, bật/tắt connector, giờ quét, "Quét ngay", log quét (tự refresh 3s khi có lần quét đang chạy).

- [ ] **Step 1: Create `frontend/app/settings/page.tsx`**

```tsx
"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type AppSettings, type ScanRun, type Seed } from "@/lib/api";
import { parseUtc, timeAgo } from "@/lib/format";

const STATUS_STYLE: Record<ScanRun["status"], string> = {
  running: "bg-blue-100 text-blue-800",
  ok: "bg-green-100 text-green-800",
  partial: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-800",
};

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

export default function SettingsPage() {
  const [seeds, setSeeds] = useState<Seed[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [scans, setScans] = useState<ScanRun[]>([]);
  const [newSeed, setNewSeed] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const loadSeeds = useCallback(() => api.listSeeds().then(setSeeds), []);
  const loadScans = useCallback(() => api.listScans(20).then(setScans), []);

  useEffect(() => {
    Promise.all([loadSeeds(), api.getSettings().then(setSettings), loadScans()]).catch((err) =>
      setMessage(`Không kết nối được backend: ${errorText(err)}`),
    );
  }, [loadSeeds, loadScans]);

  const anyRunning = scans.some((s) => s.status === "running");
  useEffect(() => {
    if (!anyRunning) return;
    const timer = setInterval(() => loadScans().catch(() => {}), 3000);
    return () => clearInterval(timer);
  }, [anyRunning, loadScans]);

  async function addSeed(e: FormEvent) {
    e.preventDefault();
    const keyword = newSeed.trim();
    if (!keyword) return;
    try {
      await api.addSeed(keyword);
      setNewSeed("");
      setMessage(null);
      await loadSeeds();
    } catch (err) {
      setMessage(err instanceof ApiError && err.status === 409 ? `“${keyword}” đã có trong watchlist` : errorText(err));
    }
  }

  async function removeSeed(id: number) {
    try {
      await api.deleteSeed(id);
      await loadSeeds();
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  async function saveSettings(body: Parameters<typeof api.updateSettings>[0]) {
    try {
      setSettings(await api.updateSettings(body));
    } catch (err) {
      setMessage(errorText(err));
    }
  }

  async function scanNow() {
    try {
      const res = await api.startScan();
      setMessage(`Đã bắt đầu quét: ${res.sources.join(", ")}`);
      await loadScans();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) setMessage("Đang có lần quét chạy, vui lòng chờ.");
      else if (err instanceof ApiError && err.status === 400) setMessage("Không có nguồn nào đang bật và đã cấu hình API key.");
      else setMessage(errorText(err));
    }
  }

  return (
    <div className="space-y-8">
      <h1 className="text-xl font-semibold">Cài đặt</h1>
      {message && <p className="rounded-md bg-zinc-100 p-3 text-sm">{message}</p>}

      <section className="space-y-3">
        <h2 className="font-semibold">Watchlist keyword</h2>
        <form onSubmit={addSeed} className="flex gap-2">
          <input
            value={newSeed}
            onChange={(e) => setNewSeed(e.target.value)}
            placeholder="vd: nurse, dog mom, fishing"
            className="w-72 rounded-md border border-zinc-300 px-3 py-1.5 text-sm"
          />
          <button className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white">Thêm</button>
        </form>
        <div className="flex flex-wrap gap-2">
          {seeds.length === 0 && <p className="text-sm text-zinc-500">Chưa có keyword nào.</p>}
          {seeds.map((s) => (
            <span key={s.id} className="flex items-center gap-1 rounded-full border border-zinc-300 bg-white px-3 py-1 text-sm">
              {s.keyword}
              <button onClick={() => removeSeed(s.id)} className="text-zinc-400 hover:text-red-600" aria-label={`Xóa ${s.keyword}`}>
                ×
              </button>
            </span>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold">Nguồn dữ liệu</h2>
        <ul className="divide-y divide-zinc-200 rounded-md border border-zinc-200 bg-white">
          {settings?.connectors.map((c) => (
            <li key={c.name} className="flex items-center gap-3 px-4 py-2 text-sm">
              <span className="w-24 font-medium">{c.name}</span>
              <span className={c.configured ? "text-green-700" : "text-zinc-400"}>
                {c.configured ? "Đã cấu hình API key" : "Chưa cấu hình (thêm vào backend/.env)"}
              </span>
              <label className="ml-auto flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={c.enabled}
                  onChange={(e) => saveSettings({ connectors_enabled: { [c.name]: e.target.checked } })}
                />
                Bật
              </label>
            </li>
          ))}
        </ul>
        {settings && (
          <label className="flex items-center gap-2 text-sm">
            Giờ quét hằng ngày (UTC):
            <select
              value={settings.scan_hour_utc}
              onChange={(e) => saveSettings({ scan_hour_utc: Number(e.target.value) })}
              className="rounded-md border border-zinc-300 bg-white px-2 py-1"
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
            <span className="text-zinc-500">= {String((settings.scan_hour_utc + 7) % 24).padStart(2, "0")}:00 giờ Việt Nam</span>
          </label>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">Lịch sử quét</h2>
          <button
            onClick={scanNow}
            disabled={anyRunning}
            className="rounded-md bg-orange-500 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {anyRunning ? "Đang quét…" : "Quét ngay"}
          </button>
        </div>
        <table className="w-full rounded-md border border-zinc-200 bg-white text-left text-sm">
          <thead className="bg-zinc-50 text-xs uppercase text-zinc-500">
            <tr>
              <th className="px-3 py-2">Nguồn</th>
              <th className="px-3 py-2">Trạng thái</th>
              <th className="px-3 py-2">Bắt đầu</th>
              <th className="px-3 py-2">Bản ghi</th>
              <th className="px-3 py-2">Lỗi</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-200">
            {scans.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-3 text-zinc-500">
                  Chưa có lần quét nào.
                </td>
              </tr>
            )}
            {scans.map((s) => (
              <tr key={s.id}>
                <td className="px-3 py-2">{s.source}</td>
                <td className="px-3 py-2">
                  <span className={`rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[s.status]}`}>{s.status}</span>
                </td>
                <td className="px-3 py-2" title={parseUtc(s.started_at).toLocaleString()}>
                  {timeAgo(s.started_at)}
                </td>
                <td className="px-3 py-2">{s.records}</td>
                <td className="max-w-md truncate px-3 py-2 text-xs text-red-700" title={s.error ?? ""}>
                  {s.error}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify lint and build**

Run: `cd frontend && npm run lint && npm run build`
Expected: no errors; routes `/products` and `/settings` built.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/settings
git commit -m "feat(frontend): add settings page for watchlist, connectors and scans

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 15: README + end-to-end verification

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create `README.md`**

````markdown
# POD Trend Radar

Ứng dụng nghiên cứu ngách & sản phẩm POD (t-shirt, sweatshirt, hoodie) bán chạy tại Mỹ.
Phase 1: connector Etsy, theo dõi Best Sellers (snapshot hằng ngày, tăng trưởng 7 ngày, 🔥), trang Cài đặt.

## Cài đặt

Yêu cầu: [uv](https://docs.astral.sh/uv/) (tự tải Python 3.12), Node 20+.

```bash
make install
cp backend/.env.example backend/.env       # điền ETSY_API_KEY
cp frontend/.env.local.example frontend/.env.local
make migrate
```

### Lấy Etsy API key
1. Đăng nhập https://www.etsy.com/developers/your-apps → **Create a new app**.
2. Copy key vào `ETSY_API_KEY` trong `backend/.env` theo đúng định dạng Etsy hướng dẫn ở trang app
   (nếu Etsy yêu cầu dạng `keystring:shared_secret` thì nhập cả hai).
3. Kiểm tra: `make smoke` → phải thấy `[ok] etsy: ... products`.

## Chạy

```bash
make dev-backend    # http://localhost:8000  (docs: /docs)
make dev-frontend   # http://localhost:3000
```

Vào **Cài đặt** → thêm keyword (vd `nurse`, `dog mom`) → **Quét ngay** → xem **Best Sellers**.
Scheduler tự quét mỗi ngày theo giờ UTC đã chọn (backend phải đang chạy).

Velocity/🔥 cần ít nhất 2 lần quét cách nhau ≥ 3 ngày.

## Test

```bash
make test           # backend unit/API tests, không gọi mạng
make smoke          # gọi thật các nguồn đã cấu hình
```

## Lưu ý
- Reviews/favorites là chỉ số proxy, không phải doanh số thật.
- Chỉ dùng cho nghiên cứu nội bộ, tần suất thấp, tuân thủ điều khoản API của từng nền tảng.
````

- [ ] **Step 2: Run full backend test suite**

Run: `make test`
Expected: all tests pass, 0 failures.

- [ ] **Step 3: Manual end-to-end check (needs a real `ETSY_API_KEY` in `backend/.env`)**

```bash
make migrate
make smoke                               # expect "[ok] etsy: 3 payloads ... products (N with image)"
make dev-backend &                       # in another terminal
curl -s -X POST localhost:8000/api/seeds -H 'Content-Type: application/json' -d '{"keyword":"nurse"}'
curl -s -X POST localhost:8000/api/scans -H 'Content-Type: application/json' -d '{}'
sleep 20; curl -s 'localhost:8000/api/scans' | head -c 400       # status "ok"
curl -s 'localhost:8000/api/products?limit=3' | head -c 800      # items with titles/images
```

Then `make dev-frontend`, open http://localhost:3000 → redirected to `/products`, cards render with images; `/settings` shows the seed, Etsy "Đã cấu hình", scan log row `ok`.

If `make smoke` shows products but `0 with image`, the `includes` param format is wrong: change `"includes": "Images,Shop"` in `backend/app/connectors/etsy.py` to `"includes": ["Images", "Shop"]` (httpx sends repeated params), re-run smoke, and update `test_fetch_runs_search_and_batch_per_product_type` if needed. Save a real fixture with `cd backend && .venv/bin/python scripts/smoke.py nurse --save` and keep it for future tests.

If no Etsy key is available, record that Step 3 was skipped and only Steps 1–2 were verified.

- [ ] **Step 4: Commit**

```bash
git add README.md backend/tests/fixtures
git commit -m "docs: add README with setup, run and verification steps

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
