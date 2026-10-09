# Niche research page + work tracking — design

Date: 2026-10-09. Approved by the user ("ok").

Features (user's numbering): 1 Top Tags, 2 13-tag generator, 3 competition, 4 price reference, 6 work tracking.

## 1. Data we already have

- `products` (source `etsy`): `title`, `price` (USD), `product_type` (tshirt|sweatshirt|hoodie), `tags` (JSON list of normalized tags, ~94% filled).
- `listing_signals.status` — breakout = `super_breakout` | `steady_grower` (`BREAKOUT_STATUSES`). The niche
  page counts `graduated` (proven sellers) as breakouts too.
- `trend_signals` source `etsy`, metrics `listing_count_tshirt|_sweatshirt|_hoodie` = Etsy's total
  search result count for "<kw> shirt|sweatshirt|hoodie". Today only for seed keywords.
- Scoring already uses `("etsy", "listing_count_tshirt")` as competition.

## 2. Backend

### 2.1 Competition counts for child niches (`app/pipeline/etsy_counts.py`, job `etsy_counts`)

- Runs as a `ScanJob` after `etsy_signals` (needs `ETSY_API_KEY`, can be disabled like other sources).
- Picks up to `MAX_KEYWORDS = 30` POD-relevant keywords from the latest `keyword_scores` (highest
  score first) that have no `etsy/listing_count_tshirt` signal in the last `REFRESH_DAYS = 3` days.
- For each keyword and each type: `GET /listings/active?keywords=<kw> <suffix>&limit=1` → `count`;
  stored as `TrendSignal(source="etsy", metric="listing_count_<type>")` for today (same as seeds).
- Own `ScanRun(source="etsy_counts")`; errors per query collected, 3 consecutive failures stop the job.

### 2.2 Niche report (`app/services/niche.py`, `GET /api/niche?keyword=<text>&product_type=<t?>`)

Niche products: Etsy products whose title contains the keyword as a whole word (`keyword_regex`) or that
are linked through `product_keywords` to the keyword (`seed_keyword_ids`), restricted to products with a
snapshot in the last 30 days. Optional `product_type` filter. 404 when the keyword text is empty.

Response:

```json
{
  "keyword": "hockey mom",
  "keyword_id": 12,            // null if the keyword is not in `keywords`
  "product_type": null,
  "listings": 140, "breakouts": 9,
  "competition": {
    "date": "2026-10-09",      // null when unknown
    "counts": {"tshirt": 17445, "sweatshirt": 9615, "hoodie": 3321},
    "level": "medium"          // low (<10k shirts) | medium (<50k) | high | null
  },
  "prices": [                  // one row per product_type present, then "all"
    {"product_type": "tshirt", "count": 80, "p25": 19.5, "median": 24.0, "p75": 28.9,
     "breakout_median": 26.0}
  ],
  "tags": [                    // up to 60, sorted by listings desc
    {"tag": "hockey mom shirt", "listings": 40, "breakouts": 5, "share": 0.29, "lift": 2.1, "rising": true}
  ],
  "generated": {
    "tags": ["hockey mom", "..."],          // exactly up to 13, each <= 20 chars, no plural duplicates
    "title_phrases": ["hockey mom shirt", "..."]  // up to 6 multi-word phrases for the title
  }
}
```

- `share = listings / niche listings`; `lift = (b + 1) / (B + 2) ÷ (n + 1) / (N + 2)` (smoothed
  breakout share over overall share); `rising = breakouts >= 2 and lift >= 1.5`.
- Generator score = `share + 2 * breakout_share`; candidates ≤ 20 chars; dedupe by `canonical_keyword`;
  the keyword itself first when ≤ 20 chars. Title phrases = top-scored tags with ≥ 2 words, any length.
- Price percentiles over `Product.price`, linear interpolation; `breakout_median` null without breakouts.

### 2.3 Trends list additions (`GET /api/trends`)

Each item gains `listing_count` (latest `etsy/listing_count_tshirt` within 7 days of the score date, or
null), `competition_level` (same thresholds) and `opportunity` = `round(100 * mean(demand, momentum ?? 0.5) * (1 - competition))`
when `competition` is known, else null. New query param `sort=score|opportunity` (default score;
opportunity puts nulls last).

### 2.4 Work tracking

Table `work_items`: `id`, `subject_kind` (`keyword`|`product`), `subject_id`, `status`
(`idea`|`designing`|`listed`|`skipped`), `note` (≤ 500 chars, nullable), `created_at`, `updated_at`;
unique (`subject_kind`, `subject_id`). Alembic migration.

API:
- `GET /api/work?status=<s?>` → `[{subject_kind, subject_id, status, note, updated_at, title, image_url, link, external_url}]`
  newest first. For keywords: `title` = keyword text, `link` = `/niche?keyword=<text>`. For products: title, image,
  `link` = `/niche?keyword=<first linked keyword>` or null, `external_url` = Etsy URL.
- `PUT /api/work/{kind}/{subject_id}` body `{"status": "...", "note": "..."|null}` → the item (404 unknown subject, 422 bad status).
- `DELETE /api/work/{kind}/{subject_id}` → 204.

Alerts: `detect_alerts` drops niche candidates whose keyword, and listing/hot_product candidates whose
product, has status `listed` or `skipped`.

## 3. Frontend

- `lib/api.ts`: types + functions for the endpoints above.
- `components/WorkStatus.tsx`: compact control (💡 Ý tưởng, 🎨 Đang thiết kế, ✅ Đã đăng, ⏸ Bỏ qua, clear) with
  optional note; used on Trend Radar rows, Watchlist cards, Signal cards, Best-seller cards and the niche page.
- `/niche` ("Phân tích ngách"): keyword input + watchlist chips when empty; sections Competition, Price,
  Top Tags (type filter, rising badge), 13 tags (copy as `a, b, c` and as `#hashtags`), title phrases.
- `/work` ("Việc của tôi"): grouped by status, note editing, links.
- Trend Radar: competition column (count + level), sort select Điểm / Cơ hội; keyword → `/niche` link.
- Nav: add Phân tích ngách and Việc của tôi.

## 4. Testing

Backend unit tests per service/API/job (respx for Etsy, never real network). Frontend: `npm run build` + lint
and a manual check in the running app.
