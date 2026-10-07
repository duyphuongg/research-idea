# Whole-word keyword matching, batched Telegram, weekly digest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** (1) Watch keywords match whole words only; (2) Telegram sends at most one notification per scan, silent unless high-priority, held during quiet hours; (3) a weekly summary message on Monday morning.

**Architecture:** Matching moves to a shared regex builder in `app/services/watchlist.py` (SQLite REGEXP for SQL, `re` in Python). `send_pending` in `app/notify/telegram.py` is rewritten to build one batch message (album/photo/text). A new `app/services/digest.py` builds the weekly HTML; `run_scan` calls `maybe_send_weekly_digest` after alert delivery.

**Tech Stack:** FastAPI, SQLAlchemy 2.1 (SQLite), httpx, respx, pytest-asyncio.

## Global Constraints

- Backend commands from `backend/`: `.venv/bin/pytest -q` (386 passing at start).
- Bot token is a secret: never logged, printed, or in exception text (see existing `_post` / `TelegramError`). Tests never reach the real Telegram API (autouse fixture `_no_real_telegram` in tests/conftest.py stays effective).
- SQLite REGEXP via SQLAlchemy `regexp_match` ignores the `flags=` argument on this setup — put `(?i)` inside the pattern.
- Telegram Bot API: `sendMediaGroup` takes 2–10 items, caption (≤1024 visible chars) on the first item shows as the album caption; `sendPhoto` caption ≤1024; `sendMessage` text ≤4096; `disable_notification: true` delivers silently.
- Copy is Vietnamese. Every commit message ends with a blank line then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit `.superpowers/`, `backend/.env`, `backend/data/`.

---

### Task 1: Whole-word keyword matching

**Files:** Modify `backend/app/services/watchlist.py`; Test `backend/tests/test_watchlist_service.py` (+ existing `tests/test_api_signals.py`, `tests/test_alerts_service.py`, `tests/test_watchlist_api.py` must keep passing).

**Produces:** `keyword_regex(keyword: str) -> str` (Python `re` pattern, no flags) used by both `listing_matches` and `listing_keyword_filter`.

Rule: normalize the keyword (`normalize_keyword`), split into words, `re.escape` each, join with `[\s\-]+`, allow an optional plural `s` on the last word, and bound it with alphanumeric lookarounds (not `\b`, which fails next to punctuation such as `%`):
```python
_EDGE_L, _EDGE_R = r"(?<![a-zA-Z0-9])", r"(?![a-zA-Z0-9])"

def keyword_regex(keyword: str) -> str:
    words = [re.escape(w) for w in normalize_keyword(keyword).split()]
    if not words:
        return r"(?!)"
    return _EDGE_L + r"[\s\-]+".join(words) + r"s?" + _EDGE_R
```
- `listing_matches(keyword, discovery_query, title, suffix)`: `discovery_query == f"{kw} {suffix}" or re.search(keyword_regex(keyword), title, re.IGNORECASE)`.
- `listing_keyword_filter(keyword, suffix)`: `or_(ListingSignal.discovery_query == f"{kw} {suffix}", Product.title.regexp_match("(?i)" + keyword_regex(keyword)))`. Remove `_like_escape` if unused.
- Empty/whitespace keyword: `keyword_regex` returns the never-matching `(?!)` (shown above).

Tests (add to test_watchlist_service.py, both Python and SQL paths via a parametrized helper that inserts titled listings and runs the filter):
| keyword | title | match |
|---|---|---|
| nurse | "Funny Nurse Shirt" | ✅ |
| nurse | "Nurses Week Tee" | ✅ (plural) |
| nurse | "Nursery Rhyme Tee" | ❌ |
| game day | "Game-Day Football Tee" | ✅ |
| game day | "Endgame Dayton Tee" | ❌ |
| football mom | "Football Moms Club" | ✅ |
| 100% | "Tennis 100% tee" | ✅ (regex escaping) |
| 100 | "Tennis 1000 tee" | ❌ |
| pickleball | "PICKLEBALL Queen" | ✅ (case) |

Update the old substring test in test_watchlist_service.py accordingly. Commit `feat(watchlist): match watch keywords as whole words`.

---

### Task 2: One Telegram notification per scan

**Files:** Modify `backend/app/notify/telegram.py`, `backend/app/analysis/alerts.py` (config), `backend/config/alerts.yaml`; Test `backend/tests/test_telegram.py` (rewrite batch tests), `backend/tests/test_alerts_config.py`.

**Config additions** (`AlertsConfig` + yaml, with Vietnamese comments):
```yaml
telegram_max_items: 5      # số tin liệt kê (kèm ảnh) trong 1 thông báo mỗi lần quét; còn lại: "… và N tin khác"
quiet_start: 22            # giờ yên lặng (giờ máy): không gửi Telegram từ 22:00 …
quiet_end: 7               # … đến 7:00; tin được giữ lại và gửi ở lần quét kế tiếp. Đặt bằng nhau để tắt.
```
`AlertsConfig` gains `quiet_start: int = 22`, `quiet_end: int = 7` (update `test_defaults_match_yaml`).

**Behaviour of `send_pending(session, settings, cfg=None, *, client=None, now=None, local_now=None) -> int`:**
1. Not configured → 0, no HTTP.
2. `local_now = local_now or datetime.now().astimezone()`; if in quiet hours (`quiet_start != quiet_end` and hour in the wrapped range [quiet_start, quiet_end)) → return 0 (nothing marked).
3. Pending = unsent, created within `PENDING_DAYS` (2). None → 0. Sort with `telegram_order`.
4. `items = pending[:max_items]`, `rest = pending[max_items:]`.
5. Build ONE HTML caption:
```
🔔 <b>{len(pending)} tin mới</b>
1. 🔥 <b>Etsy bứt phá</b> · pickleball
<a href="{app_url}{link}">{title ≤ 90 chars}</a> — {reason}
2. …
… và {len(rest)} tin khác — <a href="{app_url}/alerts">xem tất cả</a>
```
   - Escape title/reason/keyword with `html.escape` after cutting raw text (title ≤ 90, reason ≤ 120). No app link → title as plain text, and the "xem tất cả" link is dropped (keep "… và N tin khác").
   - Keep the caption's visible text (tags stripped, entities unescaped) ≤ 1024: if longer, move trailing items into `rest` and rebuild.
6. Loud vs silent: `disable_notification = not any(a.kind == "niche" or (a.kind == "listing" and a.level == 2) for a in pending)`.
7. Send: photos = image URLs of `items` (in order, skipping None).
   - ≥ 2 photos → `sendMediaGroup` with `media=[{"type": "photo", "media": url, **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {})} ...]`, `disable_notification`.
   - 1 photo → `sendPhoto` (photo, caption, parse_mode, disable_notification).
   - 0 photos → `sendMessage` (`_message(caption)` + disable_notification).
   - Media call returns 400 (bad image URL) → retry once as `sendMessage` with the same caption.
8. Status 200 → mark ALL pending (items + rest) `sent_at = now`, return `len(pending)`. 429 / other status / `TelegramError` / unexpected exception → log status or class name only, mark nothing, return 0.
- Delete `format_caption`, `_send_alert` and the per-alert loop if no longer used (keep `KIND_STYLE`, `send_text`, `_post`, `telegram_configured`, `TelegramError`). `/api/alerts/test` keeps using `send_text`.

Tests (respx; pass `local_now` explicitly in every test, e.g. `datetime(2026, 10, 8, 8, 5)` and a quiet one `datetime(2026, 10, 8, 23, 0)`):
- 7 pending, 5 with images → exactly ONE `sendMediaGroup` call; payload media has 5 items, caption only on the first, caption contains "7 tin mới", "1." … "5.", "… và 2 tin khác"; all 7 marked sent; no sendPhoto/sendMessage calls.
- Only low-priority kinds (amazon, hot_product, listing L1) → `disable_notification` true; with one niche or listing L2 → false.
- One image → sendPhoto; zero images → sendMessage.
- Media 400 → falls back to one sendMessage; marked sent.
- Quiet hours (23:00 and 06:59) → no HTTP, nothing marked; 07:00 → sends. `quiet_start == quiet_end` → never quiet.
- 429 / 500 / transport error → nothing marked, returns 0.
- Caption visible length ≤ 1024 with 5 items having 300-char titles and reasons; HTML entities intact (title containing `&` and `<`).
- Token never in logs (keep the existing httpx INFO test, adapted to the batch call).
- Not configured → no HTTP.

Commit `feat(telegram): one batched notification per scan, silent unless high-priority, quiet hours`.

---

### Task 3: Weekly digest

**Files:** Create `backend/app/services/digest.py`, `backend/scripts/digest_now.py`; Modify `backend/app/pipeline/scan.py`, `backend/app/settings_store.py` (new key), `Makefile` (`digest-now`, add to .PHONY), `README.md` (Telegram section: batching, silent, quiet hours, weekly digest, `make digest-now`); Test `backend/tests/test_digest.py`.

**Produces:**
```python
def build_digest(session: Session, today: date, app_url: str | None) -> str        # HTML, ≤ 4096 chars
async def maybe_send_weekly_digest(session, settings, *, local_now: datetime | None = None,
                                   cfg: AlertsConfig | None = None, client=None) -> bool  # True if sent
```
`settings_store.DEFAULTS["digest_last_week"] = None` (stores `"YYYY-Www"` ISO week string).

**`build_digest` sections** (omit a section entirely when it has no rows; the header always present):
```
📊 <b>Tổng kết 7 ngày qua ({today-7:%d/%m} – {today-1:%d/%m})</b>     (the window the content covers)

🚀 <b>Ngách tăng mạnh nhất 7 ngày</b>
1. football mom game day — 64 (+12)
…(top 5)
```
   - Latest score date L = max(KeywordScore.date). For pod-relevant keywords with a score on L, base = their score on the latest date ≤ L − 7 days (and ≥ L − 14). delta = score(L) − base. Top 5 with delta > 0, desc. Each keyword text links to `{app_url}/trends/{id}` when app_url is set (escaped).
   - If no keyword has a base (not enough history): heading "🚀 <b>Ngách điểm cao nhất</b>" and top 5 by score(L), shown as "— 64".
```
👀 <b>Watchlist</b>
• football mom: 58 điểm · 2 bứt phá · 3 tin
```
   - Per active seed (watch_keywords order): score = latest score of its first `seed_keyword_ids` id (or "—"); "bứt phá" = count of listings with status super_breakout/steady_grower on the latest `updated_on` matching `listing_keyword_filter(seed, suffix)`; "tin" = alerts with `watch_keyword == seed.keyword` created in the last 7 days.
```
📅 <b>Sắp tới</b>
• Halloween 31/10 — còn 24 ngày · 🔥 Cao điểm
```
   - From `load_calendar()` + `occurrences(defs, today, 60)` + `phase(...)` + `PHASE_LABEL` (app/analysis/us_calendar.py; see how app/api/calendar.py calls them). Events with start ≥ today, max 4, sorted by start. "còn N ngày"; when N == 0 → "hôm nay".
```
🔔 <b>Tuần qua:</b> 7 tin (2 🚀 · 3 🔥 · 2 🛒)
<a href="{app_url}/alerts">Mở app →</a>
```
   - Alerts created in the last 7 days, counts per kind using KIND_STYLE icons (omit zero kinds); "Tuần qua: chưa có tin" when 0. Link line only when app_url.
- All dynamic text escaped. Truncate to ≤ 4096 by dropping lines from the end of the longest section if ever needed (unlikely; a test with many seeds keeps it under the limit).

**`maybe_send_weekly_digest`:** returns False when Telegram is not configured, or in quiet hours (same rule as Task 2), or `get_setting(session, "digest_last_week") == current ISO week of local_now`. Otherwise builds the digest for `local_now.date()`, sends with `send_text` (loud), and on success stores the ISO week (`set_setting`) and returns True; on `TelegramError` logs and returns False (week not stored → retried next scan). Because scans run 08:00 and 20:00, the first scan of each ISO week (Monday 08:00, or later if the Mac was off) sends it.

**scan.py:** inside the existing Telegram try-block, after `send_pending`, `await maybe_send_weekly_digest(session, settings or get_settings())`; the existing `finally: session.commit()` persists the week marker.

**`make digest-now`** → `cd backend && .venv/bin/python scripts/digest_now.py`: builds the digest for today, prints a plain-text preview (tags stripped) to stdout, sends it via `send_text` if configured (print "Đã gửi tin tổng kết." / the TelegramError message), does NOT touch `digest_last_week`.

Tests (`tests/test_digest.py`):
- Rising section with history: keyword A 50→64 (+14), B 60→62 (+2), C 70→65 (negative, excluded), non-pod-relevant D excluded → lines in order A, B with "(+14)" "(+2)".
- Fallback heading when no history.
- Watchlist line numbers (score, breakout count with whole-word matching, alerts count in 7 days, older alert not counted).
- Upcoming section uses the calendar (use a `today` where Halloween is upcoming, e.g. 2026-10-07 → contains "Halloween" and "còn 24 ngày").
- Alerts summary counts per kind; "chưa có tin" when none.
- Escaping: keyword with `<b>` appears escaped.
- `maybe_send_weekly_digest`: sends once per ISO week (second call same week → False, one HTTP call total via respx), sends again next week, not in quiet hours, not when unconfigured, failure (500) → False and week not stored.
- run_scan integration: with the conftest no-Telegram settings, run_scan does not error and sends nothing.

Commit `feat(telegram): weekly digest on Monday morning (make digest-now)`.
