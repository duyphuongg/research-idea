# Watchlist page, keyword filter and alerts (Telegram + "Tin mới")

## Goal

The user follows a few niche keywords (Watchlist = `seeds` table; now sports: football mom, game day, pickleball, hockey mom, basketball mom, fantasy football). They want to:
1. See per keyword: its sub-niches and its Etsy breakout listings, in one place.
2. Filter Etsy Listing Signals by keyword.
3. Get told — on the phone (Telegram) and in the app ("Tin mới") — when a niche breaks out or a product turns hot, right after each scan (08:00 and 20:00).

Non-goals: per-user accounts, email/push other than Telegram, AI copy, changing scoring.

## 1. Alert rules

Detection runs once at the end of every scan (`run_scan`, after `rescore`), over the latest data. Thresholds live in `backend/config/alerts.yaml`:

```yaml
niche_min_score: 60        # 🚀 niche breakout
niche_min_growth: 0.20     # growth > 20%
amazon_top_n: 20           # 🛒 new into top N
cooldown_days: 7           # same subject not re-alerted within N days unless level rises
telegram_max_items: 5      # items with photo per scan; rest summarized
```

| Kind | `kind` | Trigger | Scope | Level |
|---|---|---|---|---|
| 🚀 Niche breakout | `niche` | latest `KeywordScore.score >= niche_min_score` and `growth > niche_min_growth`, keyword `is_pod_relevant` | seed keywords + their children via `KeywordRelation` (seed's keyword id as parent; also the canonical/singular form) | 1 |
| 🔥 Etsy listing breakout | `listing` | `ListingSignal.status` is `steady_grower` (level 1) or `super_breakout` (level 2) on the latest `updated_on` | steady_grower: listing belongs to a watchlist keyword (see §2 matching); super_breakout: any listing | 1 / 2 |
| ⭐ Hot product | `hot_product` | product is in the hot set (same `hot_ids` computation as Best Sellers, licensed excluded) | products linked via `ProductKeyword` to a watchlist keyword (only seeds have product links) | 1 |
| 🛒 Amazon new top N | `amazon` | latest `AmazonRank` for list `bestsellers` has `rank <= amazon_top_n` and the product had no `bestsellers` rank `<= amazon_top_n` in the same category on the previous rank date; `Product.licensed` false | all 8 categories | 1 |

Dedupe: an alert is identified by `(kind, subject_id)` (`subject_id` = keyword id or product id). A new alert is created only if no alert for the same key exists with `created_at` within `cooldown_days`, **or** the new level is higher than the most recent one's level (steady → super breakout).

Priority for Telegram ordering (highest first): listing L2, niche, amazon, listing L1, hot_product; ties by the item's main number (score / Δsaves / rank asc).

When the watchlist is empty, only the scope-independent rules run (super breakout, Amazon).

## 2. Keyword ↔ listing matching

A listing belongs to watchlist keyword `k` if `ListingSignal.discovery_query == f"{k} {seed_query_suffix}"` or the listing title contains `k` (case-insensitive substring of `normalize_keyword(k)`). Implemented once in `app/services/watchlist.py::listing_matches(keyword, discovery_query, title)` and reused by the Signals filter, the Watchlist page and alert scope.

## 3. Data model (Alembic migration `alerts`)

`alerts` table:

| column | type | note |
|---|---|---|
| id | int PK | |
| kind | str(20) | niche / listing / hot_product / amazon |
| subject_id | int | keyword id (niche) or product id |
| level | int | 1 or 2 |
| priority | float | ordering within a kind (score, Δsaves, velocity, −rank) |
| title | str(300) | e.g. "football mom game day" / listing title |
| reason | str(300) | Vietnamese, e.g. "Điểm 64 · tăng 35%", "+12 lượt lưu/ngày · DSR 18%", "Hạng 7 · Áo thun nữ" |
| image_url | str null | product image (null for niche) |
| link | str | in-app path: `/trends/{id}`, `/signals?keyword=…`, `/products?keyword_id=…`, `/amazon?category=…` |
| external_url | str null | Etsy/Amazon URL |
| watch_keyword | str null | watchlist keyword it belongs to, for grouping |
| scan_date | date | |
| created_at | datetime | |
| read_at | datetime null | set when "Tin mới" is opened |
| sent_at | datetime null | set after Telegram delivery |

Index on `(kind, subject_id, created_at)`.

## 4. Backend units

- `app/analysis/alerts.py` — pure: rules + dedupe, input plain dataclasses, output `list[AlertCandidate]`. Fully unit-tested.
- `app/services/alerts.py` — `detect_alerts(session, today, config) -> list[Alert]`: loads data, calls analysis, inserts rows. Called from `run_scan` after rescore inside its own try/except (alerts must never fail a scan).
- `app/services/hot.py` — the hot-product computation moved out of `api/products.py` (`compute_hot_ids(session) -> set[int]`), used by both the products API and alerts.
- `app/notify/telegram.py` — `send_pending(session, settings, config)`: if `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set, picks alerts with `sent_at IS NULL` (created in the last 2 days), sends the top `telegram_max_items` as `sendPhoto` (caption, HTML parse mode; `sendMessage` when no image), then one `sendMessage` summary "… và N tin khác — xem trong app: {APP_URL}/alerts"; marks all picked alerts `sent_at`. Network/HTTP errors are logged and leave `sent_at` null (retried next scan). Token never logged or returned by any API.
- Settings additions (`backend/.env`): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `APP_URL` (e.g. the Tailscale URL; links omitted when unset).
- `scripts/telegram_setup.py` + `make telegram-setup`: prompts for the token (hidden input), calls `getUpdates` to find the chat id of the latest private message, writes both to `backend/.env` (updating existing lines), sends a test message.

API (`app/api/alerts.py`, `app/api/watchlist.py`):
- `GET /api/alerts?limit=100` → alerts newest first + `unread` count.
- `GET /api/alerts/unread-count` → `{unread}` (sidebar badge, polled on navigation).
- `POST /api/alerts/read` → marks all unread as read.
- `POST /api/alerts/test` → sends a test Telegram message; 400 with a Vietnamese reason if not configured. `GET /api/alerts/telegram` → `{configured: bool, app_url}` (no secrets).
- `GET /api/watchlist` → per active seed: `keyword_id`, score, growth, children (top 3 by score + total count), listing counts by status (super_breakout, steady_grower), up to 4 thumbnails (best breakout first, by Δsaves), `alerts_7d` count.
- `GET /api/signals` gains `keyword` (string) filter using §2 matching.

## 5. Frontend

- Nav: Trend Radar · **Watchlist** · Listing Signals · Amazon · Bán chạy · **Tin mới** (unread badge, ink chip with mono number) · Lịch mùa vụ · Cài đặt.
- `/watchlist`: page header + add-keyword input (moved from Settings) ; grid of keyword cards (Press Room card system): keyword (Archivo), HalftoneMeter score + Delta growth, "Ngách con (n)" chips linking `/trends/{id}`, "Etsy bứt phá" counts with StatusBadges and 4 thumbnails (ImageZoom), actions "Xem chi tiết" → `/trends/{keyword_id}`, "Xem listing" → `/signals?keyword=…&status=all`, remove (×, confirm). Empty state invites adding a keyword.
- `/signals`: "Keyword" Select (Tất cả + watchlist keywords), synced with `?keyword=`.
- `/alerts` ("Tin mới"): grouped by scan date; each row: kind icon + label, image (ImageZoom) or ⊕ for niche, title, reason (mono numbers), watch keyword chip, links (in app, external). Opening the page calls `POST /api/alerts/read` after render; unread rows keep a cyan left rule for that visit. Card "Telegram": status (đã kết nối / chưa), "Gửi tin thử" button, setup hint `make telegram-setup`.
- `/amazon` reads `?category=` and `/products` reads `?keyword_id=` as initial filters (alert links land on the right view).
- `/settings`: watchlist items become links to `/trends/{keyword_id}`; add-keyword input replaced by a link "Quản lý ở trang Watchlist".

## 6. Error handling

- Alert detection or Telegram failure: logged, scan status unaffected.
- Telegram not configured: alerts still stored; Tin mới shows the setup card.
- Missing images: text-only Telegram message.
- Telegram 429: stop sending for this run (remaining stay unsent).

## 7. Testing

- `tests/test_alerts_analysis.py`: each rule's threshold edges, scope (watchlist vs global), dedupe within cooldown, level escalation re-alerts, empty watchlist.
- `tests/test_alerts_service.py`: end-to-end detect on a seeded DB; `run_scan` survives an exception in detection.
- `tests/test_telegram.py` (respx): caption/summary content, `sent_at` set on 200, left null on 500/timeout, 429 stops, no call when unconfigured, token absent from logs.
- `tests/test_watchlist_api.py`, `tests/test_alerts_api.py`, signals `keyword` filter test.
- Frontend: lint, typecheck, build; manual check of /watchlist, /alerts, /signals?keyword= at 1440 and 390 px.
