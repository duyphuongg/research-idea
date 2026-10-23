# Ideas from merchtrends.io (round 1+2) — design

Date: 2026-10-23. After comparing with merchtrends.io the user picked, in order: listing-age filter (#3), sparklines
(#5), shop pace (#4), then the spike-penalised momentum (#2) and micro-niche clustering "Ngách mới nổi" (#1).

## 1. Listing-age filter on Best Sellers ("best seller mới")

`GET /api/products?max_age=30|60|90` keeps products whose `listed_at` is at most N days before today (unknown
`listed_at` is dropped while the filter is on). Best Sellers gets a "Tuổi listing" select (Mọi tuổi / ≤ 30 / ≤ 60 /
≤ 90 ngày). Combined with the default "Tăng trưởng 7 ngày" sort this is "listing mới mà đã chạy". Signals already has
`max_age`; its page keeps its own control.

## 2. Sparklines on cards

- `ProductOut.spark`: values of the product's velocity metric (reviews/views/favorites), one per snapshot date, last
  14 days, oldest first. Best Sellers cards and shop detail cards draw it under the spec row.
- `SignalItem.spark`: saves (favorites) of the last 14 days; Signal cards draw it.
- `ShopOut.spark`: shop `sold_count` of the last 30 days; the Shop Explorer table shows it in the sales column.
- Fewer than 2 points → `—` (existing `Sparkline` behaviour).

## 3. Shop pace and estimated revenue

From existing shop metrics:
- `pace = sales_7d / prev_sales_7d` (both scaled to 7 days; only when both spans are ≥ 3 days and the previous week had ≥ 10 orders —
  smaller bases give meaningless ratios such as 1 → 15 orders = +1,400%).
  Shown as `▲ +45%` / `▼ −20%` next to 7-day sales; sort "Tăng tốc" (pace desc).
- `revenue_7d ≈ sales_7d × median price` of the shop's known products (USD only). Labelled "≈ doanh thu 7 ngày" and
  marked as an estimate; sort "Doanh thu 7 ngày".
- `ShopOut` gains `pace`, `median_price`, `revenue_7d`.

## 4. Spike-penalised momentum (drawdown penalty) for Listing Signals

Today `delta_saves` is a 1-day change, so one lucky day makes a Super Breakout. New pure function
`analysis/momentum.steady_rate(points, window=7)` over the cumulative saves series:
- daily gains between consecutive snapshots inside the last `window` days (negative gains count as 0),
  `rate = total / span_days`, `top_share = largest single gain / total`.
- `penalty = max(0, top_share − spike_share) / (1 − spike_share)`; `momentum = rate × (1 − max_penalty × penalty)`.
- Needs ≥ `min_intervals` (3) gains; otherwise `momentum = None` and the old 1-day logic is used unchanged.
- `spike = top_share > spike_share` (only when momentum is known).

Classification: when `momentum` is known it replaces `delta_saves` in the Super Breakout / Steady Grower /
Graduated saves-per-day tests, so a one-day spike no longer qualifies. Config in `listing_signals.yaml` under
`momentum:` (`window_days: 7`, `min_intervals: 3`, `spike_share: 0.6`, `max_penalty: 0.7`).

DSR also moves to the window: Δsaves/Δviews between the latest point and the oldest one inside the last 7 days.
Etsy refreshes `views` only every 1–2 days, so the old 1-day pair usually saw 0 new views → no DSR → no Super
Breakout / Steady Grower at all (0 of 13k on 2026-10-23; with the window: 52 Steady Growers, 1 Super Breakout).

Stored on `listing_signals`: `momentum`, `top_share` (migration). API: `SignalItem.momentum`, `SignalItem.spike`;
new sort `momentum` ("Tăng đều"). Card shows "Đều: +n/ngày" and a `⚡ spike 1 ngày` chip when spike. 🚀 alerts use
the stored status, so they get the penalty for free.

## 5. "Ngách mới nổi" — micro-niche clustering (Topic Velocity)

Computed once per scan (after jobs, before alerts) by `services/topics.compute_topics(session, today)` into table
`topic_snapshots` (one row per topic per date; reruns the same day replace that day).

Population: Etsy products with tags and ≥ 2 favorites snapshots, not digital, not licensed.
Per listing `gain` = favorites gained over the last 7 days scaled to 7 (≥ 3-day span, negatives → 0), and
`prev_gain` for the 7 days before that.

Topics:
1. Each tag → topic key: `canonical_keyword`, then generic words removed (shirt/tee/sweatshirt/hoodie/gift/women…,
   list in `config/topics.yaml`). Empty or < 3 chars → dropped.
2. Keep topics with ≥ `min_listings` (5) listings from ≥ `min_shops` (3) shops, where the biggest listing gain is
   ≤ `max_top_share` (50%) of the topic total (one viral listing is not a niche).
3. Merge topics whose listing sets overlap (Jaccard ≥ 0.6): the higher-scoring topic keeps its name and listings,
   the other becomes an alias.
4. Score = Bayesian velocity: `((Σ log1p(gain) + α·μ) / (n + α)) / μ` with μ = population mean of `log1p(gain)`
   and α = 10 — small topics are pulled toward the average. `growth = Σgain / Σprev_gain − 1` when prev is known.
5. Keep the top `max_topics` (100) by score.

Row fields: date, key, label, aliases, listings, shops, rising (listings with gain ≥ 3), gain_7d, prev_gain_7d,
score, growth, product_ids (top 8 by gain), ip_level (existing IP check on the label).

`GET /api/topics?sort=score|growth|new` → latest date's topics with `new` (= key not in the top list on any of the
previous 7 dates) and `series` (score per date, 30 days) + 4 sample products (image/title/url). Page `/topics`
"Ngách mới nổi": cards with label, aliases, score, growth, counts, sparkline, thumbnails, IP badge, buttons
"Nghiên cứu" (→ `/niche?keyword=`) and "Theo dõi" (adds a watch keyword).

Alert `topic` 🧭: a new topic in today's top 10 by score, not IP red; max 3 per scan, silent on Telegram (bell only for
the existing high-priority kinds). Cooldown as other alerts.
