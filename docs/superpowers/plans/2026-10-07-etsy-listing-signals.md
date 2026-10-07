# POD Trend Radar — Etsy Listing Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Theo dõi listing áo mới đăng trên Etsy (shop US), tính Δviews, Δsaves/ngày, DSR, phân loại Breakout/Steady/Graduated/Calibrating, hiển thị dạng thẻ và đưa tag của listing bứt phá vào Trend Radar.

**Architecture:** Bảng `listing_signals` (1 dòng / sản phẩm theo dõi) bên cạnh `products`/`product_snapshots` sẵn có. Module thuần `app/analysis/listing_signals.py` (cấu hình, chỉ số, phân loại). Job `etsy_signals` (`app/pipeline/listing_signals.py`) chạy trong lần quét sau các connector: tìm listing mới + cập nhật listing đang theo dõi qua Etsy API, lưu snapshot, phân loại, sinh tín hiệu tag. API `GET /api/signals`; trang `/signals`.

**Tech Stack:** như hiện tại.

**Spec:** `docs/superpowers/specs/2026-10-05-pod-trend-radar-design.md` §15.

## Global Constraints

- Chỉ listing có `shop.is_shop_us_based == true` và giá `USD`, loại áo (classify_product_type ≠ "other") — dùng lại `_to_product` của Etsy connector.
- Listing "mới": `original_creation_timestamp` (hoặc `creation_timestamp`) trong 30 ngày (`max_age_days`). Theo dõi tới 45 ngày tuổi (`track_days`), tối đa 20.000 (`max_tracked`).
- Δ tính giữa snapshot mới nhất và snapshot gần nhất cách ≥ 1 ngày trước đó, chia theo số ngày. DSR = Δsaves/Δviews (tổng trên khoảng) khi Δviews ≥ 10.
- Ngưỡng mặc định: super_breakout (age ≤ 14, Δsaves/ngày ≥ 5, DSR ≥ 0.15); graduated (age > 30, saves ≥ 30, Δsaves/ngày ≥ 1); steady_grower (Δsaves/ngày ≥ 2, DSR ≥ 0.05); calibrating khi chưa có Δ; còn lại normal. Thứ tự kiểm tra: calibrating → super_breakout → graduated → steady_grower → normal.
- Tín hiệu tag: listing super_breakout/steady_grower cập nhật hôm nay; tag đếm 1 lần/listing; ≥ 2 listing; tối đa 50 tag; `source="etsy_signals"`, `metric="breakout_tag_count"`, origin discovered; nguồn tin cậy (lọc POD như có parent).
- Etsy quota 5.000 request/ngày, 5/giây (rate limiter 0.2s). Không gọi mạng trong pytest.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

---

### Task 1: Schema + product tags + optional keyword

**Files:**
- Modify: `backend/app/models.py`, `backend/app/connectors/base.py`, `backend/app/connectors/etsy.py`, `backend/app/pipeline/store.py`
- Create: Alembic migration (autogenerate)
- Test: `backend/tests/test_models.py`, `backend/tests/test_store.py`, `backend/tests/test_etsy.py` (append)

**Interfaces:**
- Produces:
  - `Product.tags: list[str] | None` (JSON, nullable).
  - `ListingSignal(product_id PK/FK products.id, discovered_on: date, discovery_query: str, status: str = "calibrating", age_days: int | None, views: int | None, saves: int | None, delta_views: float | None, delta_saves: float | None, dsr: float | None, updated_on: date | None)`.
  - `NormalizedProduct.keyword: str | None` and new `tags: list[str] | None = None` (append after `shop_sold_count`).
  - `store.upsert_product(session, item, today) -> Product` (public; was `_upsert_product`): when `item.keyword` is None no keyword link is created; `product.tags = item.tags` only when `item.tags is not None`. `persist_batch` keeps calling it.
  - Etsy `_to_product(listing, keyword: str | None, rank: int)` fills `tags` = list of `normalize_keyword(html.unescape(t))` for each tag (non-empty, de-duplicated, order kept).

- [ ] **Step 1: Failing tests**

Append to `backend/tests/test_models.py`:

```python
from app.models import ListingSignal


def test_listing_signal_row_and_product_tags(session):
    p = Product(source="etsy", external_id="77", title="T", url="u", product_type="tshirt", tags=["a", "b"])
    session.add(p)
    session.flush()
    session.add(ListingSignal(product_id=p.id, discovered_on=date(2026, 10, 6), discovery_query="shirt"))
    session.commit()
    row = session.get(ListingSignal, p.id)
    assert (row.status, row.discovery_query, row.dsr) == ("calibrating", "shirt", None)
    assert session.get(Product, p.id).tags == ["a", "b"]
```

Append to `backend/tests/test_store.py`:

```python
from app.pipeline.store import upsert_product


def test_upsert_product_without_keyword_and_with_tags(session):
    product = upsert_product(session, make_product(keyword=None, tags=["vintage sasquatch"], views=10), D1)
    session.commit()
    assert product.tags == ["vintage sasquatch"]
    assert session.scalar(select(func.count()).select_from(ProductKeyword)) == 0
    assert session.scalar(select(ProductSnapshot)).views == 10
    upsert_product(session, make_product(keyword=None, tags=None), D2)
    session.commit()
    assert session.get(Product, product.id).tags == ["vintage sasquatch"]  # None keeps old tags
```

Append to `backend/tests/test_etsy.py`:

```python
def test_normalize_fills_normalized_tags():
    raw = RawBatch(source="etsy", payloads=[load_payload()])
    shirt = EtsyConnector("k").normalize(raw, TODAY).products[0]
    assert shirt.tags == ["nurse shirt", "nurse gift", "funny nurse", "rn shirt"]
```

(Import `func` from sqlalchemy / `ProductKeyword` in test_store.py if missing.)

- [ ] **Step 2: Run to verify failures** — `cd backend && .venv/bin/pytest tests/test_models.py tests/test_store.py tests/test_etsy.py -q`

- [ ] **Step 3: Implement**
  - models.py: in `Product` add `tags: Mapped[Any] = mapped_column(JSON, nullable=True)`; append:

```python
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
```

  - base.py: `keyword: str | None`; add `tags: list[str] | None = None` after `shop_sold_count`.
  - etsy.py `_to_product`: signature `keyword: str | None`; add `tags=_tags(listing)` where

```python
def _tags(listing: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for raw_tag in listing.get("tags") or []:
        tag = normalize_keyword(html.unescape(str(raw_tag)))
        if tag and tag not in seen:
            seen.append(tag)
    return seen
```

  - store.py: rename `_upsert_product` → `upsert_product` returning `product`; set `product.tags` when `item.tags is not None`; wrap the keyword-link block in `if item.keyword is not None:`; update `persist_batch` call.
  - `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic revision --autogenerate -m "listing signals"`; confirm it only adds `products.tags` and `listing_signals`; `.venv/bin/alembic upgrade head`.

- [ ] **Step 4: Run full suite** → pass.

- [ ] **Step 5: Commit** — `feat(backend): add listing_signals table and product tags`

---

### Task 2: Signals config, metrics, classification (pure)

**Files:**
- Create: `backend/config/listing_signals.yaml`, `backend/app/analysis/listing_signals.py`
- Test: `backend/tests/test_listing_signals_analysis.py`

**Interfaces:**
- Produces: `Thresholds` (frozen dataclass, defaults per Global Constraints: `breakout_max_age=14, breakout_min_saves_per_day=5.0, breakout_min_dsr=0.15, graduated_min_age=30, graduated_min_saves=30, graduated_min_saves_per_day=1.0, steady_min_saves_per_day=2.0, steady_min_dsr=0.05, dsr_min_delta_views=10`); `SignalsConfig(queries: tuple[str, ...], seed_query_suffix="shirt", pages_per_query=3, max_age_days=30, track_days=45, max_tracked=20000, min_tag_listings=2, max_tags=50, thresholds=Thresholds())`; `load_signals_config() -> SignalsConfig`; `ListingMetrics(age_days: int | None, views, saves, delta_views: float | None, delta_saves: float | None, dsr: float | None)`; `compute_metrics(points: list[SnapshotPoint], listed_on: date | None, today: date) -> ListingMetrics`; `classify(m: ListingMetrics, t: Thresholds) -> str`; `SIGNAL_STATUSES = ("super_breakout", "steady_grower", "graduated", "calibrating", "normal")`; `BREAKOUT_STATUSES = ("super_breakout", "steady_grower")`.

Rules: points with views or favorites present, sorted by date; latest = last; base = the most recent point with `date <= latest.date - 1 day`; no base → deltas None. span = days between. `delta_views = (latest.views - base.views) / span` (None if either views None); same for saves (favorites). DSR = `(latest.saves - base.saves) / (latest.views - base.views)` when views delta total ≥ `dsr_min_delta_views` (10) and both present, else None. `age_days = (today - listed_on).days` or None.

- [ ] **Step 1: Create `backend/config/listing_signals.yaml`**

```yaml
# Etsy Listing Signals — listing áo mới của shop US. Chỉnh tự do.
queries:
  - shirt
  - t-shirt
  - graphic tee
  - funny shirt
  - sweatshirt
  - hoodie
  - crewneck sweatshirt
  - comfort colors shirt
  - halloween shirt
  - christmas shirt
seed_query_suffix: shirt        # thêm "<seed> shirt" cho mỗi seed đang theo dõi
pages_per_query: 3              # 100 listing / trang, sắp theo ngày tạo
max_age_days: 30                # chỉ nhận listing đăng trong 30 ngày
track_days: 45                  # ngừng cập nhật sau 45 ngày tuổi
max_tracked: 20000
min_tag_listings: 2             # tag phải có ở >= 2 listing bứt phá
max_tags: 50
thresholds:
  breakout_max_age: 14
  breakout_min_saves_per_day: 5
  breakout_min_dsr: 0.15
  graduated_min_age: 30
  graduated_min_saves: 30
  graduated_min_saves_per_day: 1
  steady_min_saves_per_day: 2
  steady_min_dsr: 0.05
  dsr_min_delta_views: 10
```

- [ ] **Step 2: Failing test `backend/tests/test_listing_signals_analysis.py`**

```python
from datetime import date

import pytest

from app.analysis.listing_signals import (
    ListingMetrics,
    Thresholds,
    classify,
    compute_metrics,
    load_signals_config,
)
from app.analysis.velocity import SnapshotPoint

TODAY = date(2026, 10, 7)


def pt(d, views, saves):
    return SnapshotPoint(date=d, reviews=None, favorites=saves, views=views)


def test_load_config_from_yaml():
    cfg = load_signals_config()
    assert "graphic tee" in cfg.queries and "christmas shirt" in cfg.queries
    assert (cfg.pages_per_query, cfg.max_age_days, cfg.track_days, cfg.max_tracked) == (3, 30, 45, 20000)
    assert cfg.thresholds == Thresholds()


def test_metrics_from_two_days():
    m = compute_metrics([pt(date(2026, 10, 6), 100, 10), pt(TODAY, 160, 22)], date(2026, 10, 1), TODAY)
    assert (m.age_days, m.views, m.saves) == (6, 160, 22)
    assert m.delta_views == pytest.approx(60) and m.delta_saves == pytest.approx(12)
    assert m.dsr == pytest.approx(0.2)


def test_metrics_scale_by_span_and_pick_recent_base():
    points = [pt(date(2026, 10, 3), 10, 0), pt(date(2026, 10, 5), 50, 4), pt(TODAY, 90, 8)]
    m = compute_metrics(points, None, TODAY)
    assert m.delta_views == pytest.approx(20) and m.delta_saves == pytest.approx(2)  # base = Oct 5, span 2
    assert m.age_days is None


def test_metrics_need_a_day_apart_and_min_views_for_dsr():
    assert compute_metrics([pt(TODAY, 10, 1)], None, TODAY).delta_saves is None
    m = compute_metrics([pt(date(2026, 10, 6), 10, 1), pt(TODAY, 15, 3)], None, TODAY)
    assert m.delta_saves == pytest.approx(2) and m.dsr is None  # only 5 new views


def metrics(age, saves, dsave, dsr):
    return ListingMetrics(age_days=age, views=1000, saves=saves, delta_views=50, delta_saves=dsave, dsr=dsr)


@pytest.mark.parametrize(
    "m,expected",
    [
        (ListingMetrics(5, 10, 1, None, None, None), "calibrating"),
        (metrics(6, 22, 12, 0.2), "super_breakout"),
        (metrics(20, 22, 12, 0.2), "steady_grower"),  # too old for breakout
        (metrics(6, 22, 12, 0.10), "steady_grower"),  # DSR too low for breakout
        (metrics(35, 40, 1.5, 0.01), "graduated"),
        (metrics(10, 5, 2, 0.06), "steady_grower"),
        (metrics(10, 5, 1, 0.5), "normal"),
        (metrics(10, 5, 3, None), "normal"),  # no DSR → not steady
    ],
)
def test_classify(m, expected):
    assert classify(m, Thresholds()) == expected
```

- [ ] **Step 3: Run to verify failure**

- [ ] **Step 4: Create `backend/app/analysis/listing_signals.py`**

```python
"""Etsy Listing Signals: config, per-listing growth metrics and classification (pure)."""

from dataclasses import dataclass, field, fields
from datetime import date, timedelta

from app.analysis.velocity import SnapshotPoint
from app.config_files import load_yaml

SIGNAL_STATUSES = ("super_breakout", "steady_grower", "graduated", "calibrating", "normal")
BREAKOUT_STATUSES = ("super_breakout", "steady_grower")


@dataclass(frozen=True)
class Thresholds:
    breakout_max_age: int = 14
    breakout_min_saves_per_day: float = 5.0
    breakout_min_dsr: float = 0.15
    graduated_min_age: int = 30
    graduated_min_saves: int = 30
    graduated_min_saves_per_day: float = 1.0
    steady_min_saves_per_day: float = 2.0
    steady_min_dsr: float = 0.05
    dsr_min_delta_views: int = 10


@dataclass(frozen=True)
class SignalsConfig:
    queries: tuple[str, ...]
    seed_query_suffix: str = "shirt"
    pages_per_query: int = 3
    max_age_days: int = 30
    track_days: int = 45
    max_tracked: int = 20000
    min_tag_listings: int = 2
    max_tags: int = 50
    thresholds: Thresholds = field(default_factory=Thresholds)


@dataclass(frozen=True)
class ListingMetrics:
    age_days: int | None
    views: int | None
    saves: int | None
    delta_views: float | None
    delta_saves: float | None
    dsr: float | None


def load_signals_config() -> SignalsConfig:
    data = load_yaml("listing_signals.yaml")
    raw = data.get("thresholds") or {}
    names = {f.name: f.type for f in fields(Thresholds)}
    thresholds = Thresholds(
        **{k: (int(v) if names[k] == "int" else float(v)) for k, v in raw.items() if k in names}
    )
    defaults = SignalsConfig(queries=())
    return SignalsConfig(
        queries=tuple(str(q) for q in data.get("queries") or ()),
        seed_query_suffix=str(data.get("seed_query_suffix", defaults.seed_query_suffix)),
        pages_per_query=int(data.get("pages_per_query", defaults.pages_per_query)),
        max_age_days=int(data.get("max_age_days", defaults.max_age_days)),
        track_days=int(data.get("track_days", defaults.track_days)),
        max_tracked=int(data.get("max_tracked", defaults.max_tracked)),
        min_tag_listings=int(data.get("min_tag_listings", defaults.min_tag_listings)),
        max_tags=int(data.get("max_tags", defaults.max_tags)),
        thresholds=thresholds,
    )


def compute_metrics(points: list[SnapshotPoint], listed_on: date | None, today: date) -> ListingMetrics:
    usable = sorted(
        (p for p in points if p.views is not None or p.favorites is not None), key=lambda p: p.date
    )
    age = (today - listed_on).days if listed_on else None
    if not usable:
        return ListingMetrics(age, None, None, None, None, None)
    latest = usable[-1]
    earlier = [p for p in usable[:-1] if p.date <= latest.date - timedelta(days=1)]
    base = earlier[-1] if earlier else None
    delta_views = delta_saves = dsr = None
    if base is not None:
        span = (latest.date - base.date).days
        if latest.views is not None and base.views is not None:
            delta_views = (latest.views - base.views) / span
        if latest.favorites is not None and base.favorites is not None:
            delta_saves = (latest.favorites - base.favorites) / span
        if delta_views is not None and delta_saves is not None:
            total_views = latest.views - base.views
            if total_views >= Thresholds().dsr_min_delta_views:
                dsr = (latest.favorites - base.favorites) / total_views
    return ListingMetrics(age, latest.views, latest.favorites, delta_views, delta_saves, dsr)


def classify(m: ListingMetrics, t: Thresholds) -> str:
    if m.delta_saves is None:
        return "calibrating"
    age = m.age_days if m.age_days is not None else 0
    if (
        age <= t.breakout_max_age
        and m.delta_saves >= t.breakout_min_saves_per_day
        and m.dsr is not None
        and m.dsr >= t.breakout_min_dsr
    ):
        return "super_breakout"
    if (
        age > t.graduated_min_age
        and (m.saves or 0) >= t.graduated_min_saves
        and m.delta_saves >= t.graduated_min_saves_per_day
    ):
        return "graduated"
    if m.delta_saves >= t.steady_min_saves_per_day and m.dsr is not None and m.dsr >= t.steady_min_dsr:
        return "steady_grower"
    return "normal"
```

Note: `compute_metrics` takes an optional `dsr_min_delta_views` — make it a keyword parameter `min_dsr_views: int = Thresholds().dsr_min_delta_views` instead of reading `Thresholds()` inline, and pass `config.thresholds.dsr_min_delta_views` from the pipeline. `fields(Thresholds)` `f.type` may be a string ("int"/"float") or a type depending on annotations — handle both (compare `f.type in (int, "int")`). Wrap long lines.

- [ ] **Step 5: Run tests** → pass.

- [ ] **Step 6: Commit** — `feat(analysis): listing signal metrics and classification`

---

### Task 3: Listing Signals job (Etsy client + pipeline)

**Files:**
- Create: `backend/app/pipeline/listing_signals.py`
- Modify: `backend/app/pipeline/scan.py` (extract `start_run` / `finish_run` helpers and use them in `_run_one`)
- Test: `backend/tests/test_listing_signals_job.py`

**Interfaces:**
- Consumes: Tasks 1–2; `_to_product`, `_created_at`, `BASE_URL` from `app/connectors/etsy.py`; `RateLimiter`, `request_with_retry`, `Sleep`; `persist_batch`, `upsert_product`; `normalize_keyword`.
- Produces:
  - In scan.py: `start_run(session_factory, source: str) -> int` and `finish_run(session_factory, run_id, source, status, records, error) -> None` (the existing finalize-with-logging logic), used by `_run_one`.
  - `SOURCE = "etsy_signals"`.
  - `EtsySignalsClient(api_key, *, min_interval=0.2, sleep=asyncio.sleep)` — async context manager; `async search_new(query, pages) -> list[dict]` (GET `/listings/active` with `keywords`, `sort_on=created`, `sort_order=desc`, `limit=100`, `offset=page*100`; stop early when a page has < 100 results); `async fetch_batch(ids) -> tuple[list[dict], list[str]]` (GET `/listings/batch` with `listing_ids` comma-joined chunks of 100 and `includes=Images,Shop`; per-chunk `ConnectorError` collected into the error list). Invalid JSON → `ConnectorError`.
  - `tracked_listing_ids(session, today, config) -> set[str]` — external_ids of etsy Products that have a ListingSignal and `listed_at >= today - track_days` (or listed_at NULL and discovered_on >= today - track_days).
  - `async collect_listings(client, config, seeds, tracked, today) -> tuple[list[dict], dict[str, str], list[str]]` — runs searches for `config.queries` + `f"{seed} {config.seed_query_suffix}"` for each seed; new candidates = listing ids not tracked, first-seen query kept, created within `max_age_days`; new ids capped to `max(0, max_tracked - len(tracked))` (keep search order); fetch details for `sorted(tracked) + new_ids`; returns (details, {new_id: query}, errors).
  - `persist_listings(session, details, discovery, today, config) -> tuple[int, int]` — for each detail with `listing_id`: `_to_product(listing, None, 0)`; skip None; `upsert_product`; create `ListingSignal` only for ids in `discovery` (skip untracked others); load the product's snapshots by query, compute metrics (`compute_metrics(points, product.listed_at.date() if listed_at else None, today, min_dsr_views=...)`), set status/age_days/views/saves/deltas/dsr/updated_on. Returns (discovered, refreshed).
  - `tag_signals(session, config, today) -> NormalizedBatch` — per Global Constraints.
  - `async run_listing_signals(session_factory, api_key, keywords, today, *, config=None, client_factory=EtsySignalsClient) -> int` — `start_run(SOURCE)`; tracked ids; collect; persist listings + `persist_batch(tag_signals)` in one session, commit; status ok / partial (errors with some details) / failed (errors and no details, or exception); `finish_run`; returns run id.

- [ ] **Step 1: Failing test `backend/tests/test_listing_signals_job.py`**

```python
from datetime import date

import httpx
import respx
from sqlalchemy import select

from app.analysis.listing_signals import SignalsConfig
from app.models import ListingSignal, Product, ScanRun, TrendSignal
from app.pipeline.listing_signals import EtsySignalsClient, run_listing_signals

SEARCH_URL = "https://openapi.etsy.com/v3/application/listings/active"
BATCH_URL = "https://openapi.etsy.com/v3/application/listings/batch"
DAY1, DAY2 = date(2026, 10, 6), date(2026, 10, 7)
OCT1 = 1790812800  # 2026-10-01 UTC
OLD = 1754006400  # 2025-08-01 UTC
US = {"shop_id": 1, "shop_name": "UsShop", "is_shop_us_based": True, "transaction_sold_count": 50}
CONFIG = SignalsConfig(queries=("shirt",), pages_per_query=1)


async def no_sleep(_):
    return None


def client_factory(key):
    return EtsySignalsClient(key, min_interval=0, sleep=no_sleep)


def listing(lid, title, views, saves, tags, created=OCT1, shop=US, currency="USD"):
    return {
        "listing_id": lid, "title": title, "views": views, "num_favorers": saves, "tags": tags,
        "price": {"amount": 2500, "divisor": 100, "currency_code": currency},
        "url": f"https://www.etsy.com/listing/{lid}", "original_creation_timestamp": created,
        "images": [{"url_570xN": f"https://img/{lid}.jpg"}], "shop": shop,
    }


def day(views_501, saves_501, views_502, saves_502):
    details = [
        listing(501, "Vintage Sasquatch Shirt", views_501, saves_501, ["vintage sasquatch", "funny cryptid"]),
        listing(502, "Sasquatch Camping Tee", views_502, saves_502, ["Vintage Sasquatch", "camping shirt"]),
        listing(503, "Old Shirt", 10, 1, ["old"], created=OLD),
        listing(504, "Foreign Shirt", 10, 1, ["x"], shop={**US, "is_shop_us_based": False}),
    ]
    search = {"count": 4, "results": [{k: d[k] for k in ("listing_id", "original_creation_timestamp")} for d in details]}
    return search, {"count": 4, "results": details}


async def run_day(session_factory, today, data):
    search, batch = data
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(200, json=search))
        respx.get(url__startswith=BATCH_URL).mock(return_value=httpx.Response(200, json=batch))
        return await run_listing_signals(
            session_factory, "k", [], today, config=CONFIG, client_factory=client_factory
        )


async def test_two_days_classify_and_emit_tag_signals(session_factory):
    run1 = await run_day(session_factory, DAY1, day(100, 10, 50, 2))
    with session_factory() as s:
        assert s.get(ScanRun, run1).status == "ok"
        signals = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert set(signals) == {"501", "502"}  # old and non-US skipped
        assert {r.status for r in signals.values()} == {"calibrating"}
        assert signals["501"].discovery_query == "shirt"
        assert s.scalars(select(TrendSignal)).all() == []

    await run_day(session_factory, DAY2, day(160, 22, 80, 4))
    with session_factory() as s:
        rows = {s.get(Product, r.product_id).external_id: r for r in s.scalars(select(ListingSignal))}
        assert rows["501"].status == "super_breakout"
        assert (rows["501"].delta_saves, round(rows["501"].dsr, 2), rows["501"].age_days) == (12.0, 0.2, 6)
        assert rows["502"].status == "steady_grower"
        assert s.get(Product, rows["501"].product_id).tags == ["vintage sasquatch", "funny cryptid"]
        tags = {(t.source, t.metric, t.value) for t in s.scalars(select(TrendSignal))}
        assert tags == {("etsy_signals", "breakout_tag_count", 2.0)}  # only "vintage sasquatch" on >= 2


async def test_search_failure_is_partial_and_isolated(session_factory):
    with respx.mock:
        respx.get(url__startswith=SEARCH_URL).mock(return_value=httpx.Response(404))
        run_id = await run_listing_signals(
            session_factory, "k", ["nurse"], DAY1, config=CONFIG, client_factory=client_factory
        )
    with session_factory() as s:
        run = s.get(ScanRun, run_id)
        assert run.status == "failed" and "HTTP 404" in run.error
        assert run.source == "etsy_signals"
```

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Refactor scan.py** — add:

```python
def start_run(session_factory: sessionmaker[Session], source: str) -> int:
    with session_factory() as session:
        run = ScanRun(source=source, status="running")
        session.add(run)
        session.commit()
        return run.id


def finish_run(
    session_factory: sessionmaker[Session], run_id: int, source: str,
    status: str, records: int, error: str | None,
) -> None:
    try:
        with session_factory() as session:
            run = session.get(ScanRun, run_id)
            run.status = status
            run.records = records
            run.error = error
            run.finished_at = utcnow()
            session.commit()
    except Exception:
        logger.exception("Could not finalize scan run %s for %s", run_id, source)
```

and make `_run_one` use them (behaviour unchanged; existing tests must still pass).

- [ ] **Step 4: Create `backend/app/pipeline/listing_signals.py`** implementing the interfaces above. Key code:

```python
"""Etsy Listing Signals job: discover new US apparel listings, track them daily, classify."""

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.listing_signals import (
    BREAKOUT_STATUSES,
    SignalsConfig,
    classify,
    compute_metrics,
    load_signals_config,
)
from app.analysis.velocity import SnapshotPoint
from app.connectors.base import ConnectorError, NormalizedBatch, NormalizedSignal
from app.connectors.etsy import BASE_URL, _created_at, _to_product
from app.connectors.http import RateLimiter, Sleep, request_with_retry
from app.keywords import normalize_keyword
from app.models import ListingSignal, Product, ProductSnapshot
from app.pipeline.scan import MAX_ERROR_LEN, finish_run, start_run
from app.pipeline.store import persist_batch, upsert_product

logger = logging.getLogger(__name__)
SOURCE = "etsy_signals"
PAGE_SIZE = 100
BATCH_SIZE = 100


class EtsySignalsClient:
    def __init__(self, api_key: str, *, min_interval: float = 0.2, sleep: Sleep = asyncio.sleep):
        self.api_key = api_key
        self._sleep = sleep
        self._limiter = RateLimiter(min_interval, sleep=sleep)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "EtsySignalsClient":
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, headers={"x-api-key": self.api_key}, timeout=30.0
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        response = await request_with_retry(
            self._client, "GET", path, params=params, limiter=self._limiter, sleep=self._sleep
        )
        try:
            return response.json()
        except ValueError as exc:
            raise ConnectorError(f"invalid JSON from {path}") from exc

    async def search_new(self, query: str, pages: int) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(pages):
            data = await self._get_json(
                "/listings/active",
                {"keywords": query, "sort_on": "created", "sort_order": "desc",
                 "limit": PAGE_SIZE, "offset": page * PAGE_SIZE},
            )
            batch = data.get("results", [])
            results.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
        return results

    async def fetch_batch(self, ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
        details: list[dict[str, Any]] = []
        errors: list[str] = []
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start : start + BATCH_SIZE]
            try:
                data = await self._get_json(
                    "/listings/batch", {"listing_ids": ",".join(chunk), "includes": "Images,Shop"}
                )
                details.extend(data.get("results", []))
            except ConnectorError as exc:
                errors.append(f"batch {start}: {exc}")
        return details, errors
```

Then `tracked_listing_ids`, `collect_listings`, `persist_listings`, `tag_signals`, `run_listing_signals` per the Interfaces section (load snapshots with `select(ProductSnapshot).where(ProductSnapshot.product_id == product.id)`; `SnapshotPoint(s.date, s.reviews, s.favorites, s.views)`; tag counting with `normalize_keyword` and a per-listing set; the run catches `Exception` like `_run_one`, logs, and always calls `finish_run`).

Note: in the failure test, the batch fetch is skipped because there are no ids (search failed, nothing tracked) → details empty + errors → status "failed".

- [ ] **Step 5: Run tests** — new tests + full suite pass.

- [ ] **Step 6: Commit** — `feat(pipeline): add Etsy Listing Signals job`

---

### Task 4: Wire the job into scans, settings, relevance and scoring

**Files:**
- Create: `backend/app/pipeline/jobs.py`
- Modify: `backend/app/pipeline/scan.py`, `backend/app/services/scans.py`, `backend/app/scheduler.py`, `backend/app/api/scans.py`, `backend/app/main.py`, `backend/app/connectors/registry.py`, `backend/app/pipeline/store.py`, `backend/app/pipeline/rescore.py`, `backend/app/analysis/scoring.py`, `backend/tests/conftest.py`
- Test: append to `backend/tests/test_scan.py`, `backend/tests/test_api_scans_health.py`, `backend/tests/test_store.py`, `backend/tests/test_rescore.py`, `backend/tests/test_api_seeds_settings.py`

**Interfaces:**
- `jobs.py`: `ScanJob(name: str, run: Callable[[sessionmaker[Session], list[str], date], Awaitable[int]])` (frozen dataclass); `JobFactory = Callable[[Settings, dict[str, bool], list[str] | None], list[ScanJob]]`; `build_jobs(settings, overrides, only=None)` → `[ScanJob("etsy_signals", lambda sf, kw, today: run_listing_signals(sf, settings.etsy_api_key, kw, today))]` when `settings.etsy_api_key` and `overrides.get("etsy_signals", True)` and (`only is None` or `"etsy_signals" in only`), else `[]`.
- `run_scan(session_factory, connectors, *, jobs: Sequence[ScanJob] = (), today=None, retention_days=30)`: after connectors, `for job in jobs: run_ids.append(await job.run(session_factory, keywords, today))` (each wrapped in try/except that logs — the job records its own ScanRun), then rescore and purge as now.
- services: `resolve_jobs(app, session, only=None) -> list[ScanJob]` via `app.state.job_factory(settings, overrides, only)`; `execute_scan(app, connectors, jobs=())` passes jobs.
- `create_app(..., job_factory: JobFactory = build_jobs)` sets `app.state.job_factory`.
- POST /api/scans: 400 only when no connectors AND no jobs; `ScanStarted.sources` = connector names + job names. Scheduler: same (skip only when both empty).
- registry `connector_status`: append `{"name": "etsy_signals", "kind": "signals", "configured": bool(settings.etsy_api_key), "enabled": overrides.get("etsy_signals", True)}` (so Settings toggle + health banner include it; `PUT /api/settings` accepts "etsy_signals").
- conftest `make_client`: `kwargs.setdefault("job_factory", lambda settings, overrides, only: [])` so tests never hit the network.
- Trusted sources: `TRUSTED_SOURCES = frozenset({"etsy_signals"})` in `app/pipeline/store.py`; `_upsert_signal` uses `has_parent = signal.parent is not None or signal.source in TRUSTED_SOURCES`. `refilter` treats a keyword as having a parent if it has a KeywordRelation as child OR any TrendSignal with source in TRUSTED_SOURCES.
- scoring: add `"etsy_signals": "breakout_tag_count"` to `PRIMARY_METRICS`.

- [ ] **Step 1: Failing tests** (write them; examples):
  - test_scan.py: `run_scan(session_factory, [], jobs=[ScanJob("j", fake_run)], today=TODAY)` calls `fake_run(session_factory, ["nurse"], TODAY)` once and includes its returned id; a job that raises doesn't stop rescore (a KeywordScore still gets written for a seeded signal).
  - test_api_scans_health.py: with `make_client(connector_factory=lambda *a: [], job_factory=lambda *a: [ScanJob("etsy_signals", fake)])` POST /api/scans → 202 and `sources == ["etsy_signals"]`; with both empty → 400.
  - test_api_seeds_settings.py: update `test_settings_defaults` expected connectors to also include `{"name": "etsy_signals", "kind": "signals", "configured": True, "enabled": True}` (last); `PUT {"connectors_enabled": {"etsy_signals": false}}` → 200 and reflected.
  - test_store.py: a parentless `etsy_signals` signal for "vintage sasquatch" creates a relevant keyword (same text from `google_daily` without parent would be irrelevant).
  - test_rescore.py: `refilter` keeps an etsy_signals-only keyword relevant.
  - test_scoring.py: a keyword with only `("etsy_signals","breakout_tag_count")` recent points is scored with sources `("etsy_signals",)`.
- [ ] **Step 2: Run to verify failures.**
- [ ] **Step 3: Implement** per Interfaces (keep existing behaviour for current tests; update `execute_scan` callers).
- [ ] **Step 4: Full suite** → pass, no warnings.
- [ ] **Step 5: Commit** — `feat(scan): run Listing Signals job in scans and feed breakout tags to Trend Radar`

---

### Task 5: Signals API

**Files:**
- Create: `backend/app/api/signals.py`
- Modify: `backend/app/api/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_api_signals.py`

**Interfaces:**
- `GET /api/signals?status=signals|all|<status>&max_age=&sort=delta_saves|dsr|delta_views|newest&limit=60&offset=0`
  - `status="signals"` (default) = super_breakout + steady_grower + graduated; `all` = everything; else one status (422 if not in SIGNAL_STATUSES/"signals"/"all").
  - `max_age` (int ≥ 1, optional): `age_days <= max_age`.
  - sort: `delta_saves` (default, desc, None last), `dsr` (desc, None last), `delta_views` (desc, None last), `newest` (listed_at desc); ties by product id.
  - Only rows with `updated_on` = the latest `updated_on` in the table (stale rows hidden).
- Response `SignalPage {updated_on: date | null, counts: dict[str, int] (per status among latest rows), total, items: [SignalItem]}`; `SignalItem {product_id, title, url, image_url, shop_name, shop_sold_count, price, currency, product_type, listed_at, age_days, views, saves, delta_views, delta_saves, dsr, status, discovery_query, tags: list[{tag, keyword_id | null}]}` — keyword_id = id of the Keyword whose text equals `canonical_keyword(tag)` or the tag itself (None if absent).

- [ ] **Step 1: Failing test** — seed two products with ListingSignal rows on the same updated_on (super_breakout with tags ["vintage sasquatch"] and an existing Keyword "vintage sasquatch"; normal), plus an older updated_on row; assert default list returns only the breakout row, `counts == {"super_breakout": 1, "normal": 1}`, tag keyword_id resolved; `status=all` returns 2; `sort=newest` order; `max_age=3` filters; `status=bogus` → 422; empty DB → `{"updated_on": None, "counts": {}, "total": 0, "items": []}`.
- [ ] **Step 2–4:** implement (`selectinload` not needed; join ListingSignal↔Product), register router (`signals` module) in main.py, run full suite.
- [ ] **Step 5: Commit** — `feat(api): add listing signals endpoint`

---

### Task 6: Listing Signals page

**Files:**
- Modify: `frontend/lib/api.ts`, `frontend/app/layout.tsx`
- Create: `frontend/app/signals/page.tsx`, `frontend/components/SignalCard.tsx`

**Interfaces:** `api.listSignals(q)` with `SignalQuery {status?, max_age?, sort?, limit?, offset?}`; types `SignalItem`, `SignalPage`; nav link "Listing Signals" after "Trend Radar".

Page requirements (Vietnamese UI, keyed-result fetch pattern like `/products`):
- Header "Etsy Listing Signals" + note: "Listing áo mới (≤ 30 ngày) của shop ở Mỹ, cập nhật hằng ngày. Lượt lưu = favorites; DSR = lượt lưu mới / lượt xem mới. Cần ≥ 2 lần quét để có tín hiệu."; show `updated_on`.
- Status tabs with counts: Tất cả tín hiệu (signals) · 🚀 Super Breakout · 📈 Steady Grower · 🎓 Graduated · ⏳ Calibrating · Tất cả.
- Age filter: Mọi tuổi / ≤ 7 ngày / ≤ 14 ngày / ≤ 30 ngày. Sort: Δ lượt lưu · DSR · Δ lượt xem · Mới nhất.
- Grid of `SignalCard`: image, status badge, "{age} ngày tuổi", price, shop (+ "đã bán N" if shop_sold_count), title (2 lines, links to Etsy, new tab), stats row: VIEWS {views} (+{delta_views}/ngày), LƯU {saves} (+{delta_saves}/ngày), DSR {pct}; tags as chips (first 4) — chips with keyword_id link to `/trends/{id}`.
- Empty state: "Chưa có dữ liệu — bấm “Quét ngay” trong Cài đặt; tín hiệu xuất hiện sau 2 ngày quét."
- Pagination like /products (60 per page).

- [ ] Steps: implement, `npm run lint && npm run build` (route `/signals`), commit `feat(frontend): add Listing Signals page`.

---

### Task 7: README + live run

- [ ] Add README section "Etsy Listing Signals" (what it tracks, US-only, statuses, thresholds file `backend/config/listing_signals.yaml`, needs 2 daily scans, Etsy quota ≈ 500 requests/day).
- [ ] `make test`; frontend lint/build.
- [ ] Live (real Etsy key in backend/.env): `make migrate`; start backend; `POST /api/scans {"sources": ["etsy_signals"]}`; poll `/api/scans` until done; report the etsy_signals run status/records/error, number of ListingSignal rows, Etsy `x-remaining-today` if visible in logs (optional), and `GET /api/signals?status=all&limit=3`. (All will be "calibrating" on the first day — expected.) Check `/signals` returns 200 from the built frontend. Stop servers.
- [ ] Commit `docs: document Etsy Listing Signals`.
