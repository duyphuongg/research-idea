# Etsy Shop Explorer + shop watchlist — Design & Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Show which US Etsy shops are actually selling (orders in the last 7/30 days from daily snapshots of the shop's lifetime `transaction_sold_count`), let the user filter them by niche, watch shops, and get a 🏪 alert when a watched shop accelerates. Modelled on merchtrends.io "Shop Explorer" + "Watchlist" (user-approved design, 2026-10-09).

**Architecture:** Every Etsy listing payload already embeds its `shop` object (`includes=Images,Shop`). The Etsy connector and the Listing Signals job pass a `ShopInfo` with each normalized product; `upsert_product` upserts a `shops` row and today's `shop_snapshots` row (one per UTC date, overwritten by the evening scan). Watched shops are refreshed directly with `GET /application/shops/{shop_id}` each scan. `app/services/shops.py` derives metrics; `/api/shops*` serves the UI; alert rule + digest section reuse the existing alerts pipeline.

**Tech Stack:** FastAPI, SQLAlchemy 2.1, Alembic, SQLite, httpx/respx, pytest-asyncio; Next.js 16 App Router + Tailwind v4 ("Press Room" UI in frontend/components/ui/).

## Global Constraints

- Backend from `backend/`: `.venv/bin/pytest -q` (401 passing at start). Frontend from `frontend/`: `npm run lint`, `npx tsc --noEmit`, `npm run build`.
- Etsy only, official Open API v3 (`x-api-key` header; key in `backend/.env`, never printed). Quota 5000 req/day, 5 req/s — the watched-shop refresh adds ≤ 1 request per watched shop per scan.
- Only US shops (`is_shop_us_based is True`) are stored, matching the listing filter.
- Missing history is shown as missing, never as 0: deltas need ≥ 2 snapshots; when the oldest usable snapshot is younger than the window, return the delta with its actual `days` span (UI: "+12 (3 ngày)").
- Whole-word niche matching reuses `keyword_regex` from `app/services/watchlist.py` (SQLite REGEXP needs `(?i)` inside the pattern).
- Alerts: new kind `shop`, level 1, silent (not high-priority) in the batched Telegram notification; thresholds in `backend/config/alerts.yaml`: `shop_min_sales_7d: 30`, `shop_growth: 1.5`. Only watched shops alert.
- UI copy Vietnamese; reuse Press Room components (Card, Section, PageHeader, Select, Checkbox, Tabs, Button/ButtonLink, EmptyState, Notice, Delta, HalftoneMeter, ImageZoom, StatusBadge); 390px without horizontal page scroll (tables scroll inside their Card).
- Every commit message ends with a blank line then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit `.superpowers/`, `backend/.env`, `backend/data/`, `frontend/.env.local`. Never run anything that reaches the user's real Telegram bot (`make scan-now`, `make digest-now`).

---

### Task 1: Shop data model and capture

**Files:** `backend/app/models.py`, new Alembic migration, `backend/app/connectors/base.py`, `backend/app/connectors/etsy.py`, `backend/app/pipeline/store.py`, tests (`tests/test_shops_store.py`, extend `tests/test_etsy.py`, `tests/test_listing_signals_job.py`).

**Produces:**
```python
# app/connectors/base.py
@dataclass(frozen=True)
class ShopInfo:
    shop_id: int; name: str; url: str | None; icon_url: str | None
    opened_at: datetime | None          # from create_date (epoch seconds), naive UTC
    sold_count: int | None              # transaction_sold_count
    favorers: int | None                # num_favorers
    listing_count: int | None           # listing_active_count
    review_average: float | None; review_count: int | None
NormalizedProduct.shop: ShopInfo | None = None

def shop_info_from_payload(shop: dict) -> ShopInfo | None   # in app/connectors/etsy.py; None if no shop_id or not US-based

# app/models.py
class Shop(Base): __tablename__ = "shops"
    id (int PK = Etsy shop_id, autoincrement=False), name, url, icon_url, opened_at,
    first_seen (date), last_seen (date), watched_at (datetime | None)   # watchlist flag
class ShopSnapshot(Base): __tablename__ = "shop_snapshots"; UniqueConstraint(shop_id, date)
    id, shop_id FK shops.id, date, sold_count, favorers, listing_count, review_average, review_count
Product.shop_id: int | None  (FK shops.id, nullable)

# app/pipeline/store.py
def upsert_shop(session, info: ShopInfo, today: date) -> Shop   # upsert row + today's snapshot (overwrite same date)
```
- `_to_product` sets `shop=shop_info_from_payload(listing.get("shop") or {})`; `upsert_product` calls `upsert_shop` when `item.shop` and sets `product.shop_id`.
- Migration adds the two tables + `products.shop_id` (batch_alter_table for SQLite). Apply with `.venv/bin/alembic upgrade head` (real DB — intended).
- Tests: payload → ShopInfo fields; non-US → None; upsert twice same day → one snapshot with latest values; next day → two snapshots; product gets shop_id; listing-signals job path also records shops (fixture listings with a `shop` dict).
- Commit `feat(shops): capture Etsy shops and daily shop snapshots`.

### Task 2: Shop metrics and API

**Files:** new `backend/app/services/shops.py`, new `backend/app/api/shops.py` (+ register in `app/main.py`), `backend/app/api/schemas.py`; tests `tests/test_shops_service.py`, `tests/test_api_shops.py`.

**Produces:**
```python
@dataclass(frozen=True)
class Delta: value: int; days: int          # value over an actual span of `days`
@dataclass(frozen=True)
class ShopMetrics:
    shop: Shop; sold_count: int | None; listing_count: int | None; review_average: float | None
    sales_7d: Delta | None; sales_30d: Delta | None; prev_sales_7d: Delta | None; favorers_7d: Delta | None
    sales_per_listing: float | None          # sold_count / listing_count (None if 0/None)
def window_delta(points: list[tuple[date, int | None]], latest: date, days: int) -> Delta | None
    # latest value minus the value at the newest snapshot with date <= latest - days;
    # if none that old, use the oldest snapshot (days = actual span); None if < 2 points or span 0
def shop_metrics(session, shop_ids: Iterable[int] | None = None) -> list[ShopMetrics]   # bulk queries
def shops_matching(session, keyword: str) -> set[int]   # shops with ≥1 product whose title matches keyword_regex
```
`prev_sales_7d` = the 7-day delta ending 7 days before the latest snapshot (needs ≥ 14 days; else None).

**API:**
- `GET /api/shops?q=&min_sales=&listings=&min_spl=&opened=&min_rating=&watched=&sort=&order=&limit=50&offset=0` → `{total, latest_date, items: [ShopOut]}`.
  - `min_sales` int (1000/5000/10000/50000); `listings` one of `lt200|200_1000|gt1000`; `min_spl` int (15/30/50); `opened` one of `2026|2025plus|2024plus|before2024` (opened year = 2026 / ≥ 2025 / ≥ 2024 / < 2024); `min_rating` float (4.5/4.8); `watched` bool.
  - `sort` one of `sales_7d` (default) | `sales_30d` | `sold_count` | `sales_per_listing` | `opened_at` | `listing_count` | `review_average` | `last_seen`; `order` desc (default) | asc; None values always last.
  - `ShopOut = {id, name, url, icon_url, opened_year, listing_count, sold_count, sales_7d: {value, days} | null, sales_30d, favorers_7d, sales_per_listing, review_average, review_count, watched: bool, last_seen}`.
- `GET /api/shops/{id}` → ShopOut + `series: [{date, sold_count, favorers}]` (≤ 90 days) + `products: [ProductCard-compatible items]` (reuse the products API item shape via `_to_out`/compute_product_metrics where practical, else a minimal `{id,title,url,image_url,price,currency,product_type}` list, newest first, ≤ 24) — 404 if unknown.
- `POST /api/shops/{id}/watch` / `DELETE /api/shops/{id}/watch` → ShopOut (sets/clears `watched_at`); 404 if unknown.
- Tests cover window_delta edge cases (missing history, short span, exact 7 days, None values), filters, sort with None-last, q whole-word matching, watch toggling, 404s.
- Commit `feat(shops): shop metrics and /api/shops`.

### Task 3: Watched-shop refresh, 🏪 alert, digest section

**Files:** `backend/app/pipeline/listing_signals.py` (or a small `backend/app/pipeline/shops.py` called from the Listing Signals job with the same client), `backend/app/analysis/alerts.py`, `backend/app/services/alerts.py`, `backend/config/alerts.yaml`, `backend/app/notify/telegram.py` (KIND_STYLE/KIND_RANK), `backend/app/services/digest.py`; tests.

- **Refresh:** after Listing Signals tracking, for each shop with `watched_at` not null: `GET /application/shops/{shop_id}` via the existing `EtsySignalsClient` (same limiter/retries), `upsert_shop` with the response (US check same as listings). A failing shop is logged and skipped; never fails the job. Tests with respx.
- **Alert rule** (pure, in analysis/alerts.py): `ShopRow(shop_id, name, url, icon_url, sales_7d: int, days_7d: int, prev_sales_7d: int | None)`; candidate when `days_7d >= 7` and `sales_7d >= cfg.shop_min_sales_7d` and (`prev_sales_7d is None` or `sales_7d >= cfg.shop_growth * max(prev_sales_7d, 1)`); kind `shop`, level 1, priority = sales_7d, title = shop name, reason `"+{sales_7d} đơn/7 ngày"` + (`" (tuần trước +{prev})"` when prev known), image = icon_url, link `/shops/{id}`, external_url = shop url, watch_keyword None. Service loads rows for watched shops via `shop_metrics`. Dedupe/cooldown as other kinds. Config fields `shop_min_sales_7d: int = 30`, `shop_growth: float = 1.5` (+ yaml with Vietnamese comments, + config test).
- **Telegram:** `KIND_STYLE["shop"] = ("🏪", "Shop tăng tốc")`; `KIND_RANK[("shop", 1)]` between amazon's old slot and hot_product (i.e. after listing L1); not high-priority (silent).
- **Digest:** new section after Watchlist: `🏪 <b>Shop ra đơn nhiều nhất 7 ngày</b>` — top 3 shops by `sales_7d.value` (only `days >= 7`) among shops matching any watch keyword (`shops_matching`), line `• {name} — +{n} đơn` linked to `{app_url}/shops/{id}`; omitted when no rows.
- Commit `feat(shops): refresh watched shops, 🏪 shop alert, digest top shops`.

### Task 4: Frontend — Shop page, detail, Watchlist section

**Files:** `frontend/lib/api.ts`, `frontend/components/ui/AppShell.tsx` (nav "Shop" `/shops` after "Listing Signals"), new `frontend/app/shops/page.tsx`, `frontend/app/shops/[id]/page.tsx`, `frontend/app/watchlist/page.tsx` (+ component), `frontend/app/alerts/page.tsx` (kind `shop` label 🏪 "Shop tăng tốc").

- `/shops`: PageHeader eyebrow "Shop Explorer" + date; title "Shop đang ra đơn"; description "Shop Etsy ở Mỹ app đang thấy, xếp theo số đơn bán thêm. Số đơn tính từ tổng đơn của shop chụp mỗi ngày."
  - Search input (niche keyword, debounced) + Selects for each filter + sort Select + order toggle; quick-filter chips: "Đang lên 7 ngày" (sort sales_7d), "Shop mới 2025–2026" (opened=2025plus), "Ít listing bán nhiều" (listings lt200 + min_spl 30), "Shop lớn" (min_sales 50000). Filters sync to the URL query.
  - Table in a Card (horizontal scroll inside): shop (icon 28px + name link to `/shops/{id}`, ↗ Etsy link), Mở năm, Listing, Tổng đơn, **+Đơn 7 ngày** (mono; when days < 7 show small "(n ngày)"; null → "—"), +Đơn 30 ngày, Đơn/listing, ★ rating, ☆/★ watch toggle button (aria-pressed). Pagination 50/page. EmptyState when no shops.
  - Notice (info) while history < 7 days: "Số đơn 7 ngày cần đủ 7 ngày dữ liệu — hiện tính từ {n} ngày."
- `/shops/[id]`: header (icon, name, Etsy link, opened, listings, rating, watch button); spec cells: Tổng đơn, +7 ngày, +30 ngày, Đơn/listing, +Yêu thích 7 ngày; Recharts line of sold_count over time (ink); product grid (reuse ProductCard if the API returns that shape, else small cards with ImageZoom).
- `/watchlist`: new Section "Shop đang theo dõi" (above or below keyword cards) using `/api/shops?watched=true&sort=sales_7d`: compact table (name, +7d, +30d, tổng đơn, +yêu thích 7d, bỏ theo dõi); empty state: "Chưa theo dõi shop nào — bấm ☆ ở trang Shop."
- Verify lint/tsc/build; `make down && make up NO_OPEN=1` and check pages at 1440/390.
- Commit `feat(ui): Shop Explorer, shop detail and watched shops`.

### Task 5: Docs

README: section "Shop Explorer" (what the numbers mean, missing history, watch + 🏪 alert thresholds, digest section). Commit `docs: Shop Explorer`.
