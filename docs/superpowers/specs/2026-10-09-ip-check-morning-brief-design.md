# IP risk check + morning brief — design

Date: 2026-10-09. User picked ideas 1 (trademark check) and 2 ("Hôm nay làm gì" Telegram).

## 1. IP risk check

USPTO has no free public phrase-search API (tmsearch's internal API refuses outside calls, TSDR/ODP need a key and
look up by serial number), so the check is local and explains itself; each result links to USPTO search for a manual
check: `https://tmsearch.uspto.gov/search/search-information`.

Terms (normalized like `nfl_match.tokens`: lowercase alnum, suffixes dropped, singularized; matched as whole n-grams
of up to 5 tokens):
- `config/ip_terms.yaml` (user-editable): `league` (NFL, Super Bowl, World Series, March Madness, …) → red;
  `brand` / `character` / `celebrity` → red; `slogan` (team/fan slogans such as "who dey", "bills mafia") → yellow;
  `generic_nicknames` = team nicknames too common to flag alone (heat, magic, thunder, …).
- ESPN teams of NFL/MLB/NBA/NHL (table `sports_teams`, refreshed weekly by the hourly job): full name
  ("dallas cowboys") → red, "<location> <sport word>" not flagged, nickname alone ("cowboys") → yellow unless generic.
- NFL players (`nfl_players`) full name → red (right of publicity).

`check(text) → {level: red|yellow|green, hits: [{term, category, level}]}`; level = worst hit. Index cached in-process
for 10 minutes.

Uses:
- `POST /api/ip/check {texts: [≤ 50 strings]}` → `{uspto_url, results: [{text, level, hits}]}`.
- Niche report: every `tags[]` item gets `ip_level`; `generated.tags` and `generated.title_phrases` drop red items and
  `generated.removed` lists `{tag, term}` that were dropped; `generated.ip` maps each kept tag to its level.
- NFL moments: `ip_level` per item.
- Morning brief opportunities skip red keywords.

## 2. Morning brief ("Hôm nay làm gì")

One Telegram text message per day, sent by the first scan run between 07:00 and 12:00 local time (the 08:00 scan),
setting `brief_last_date`. Sections (each skipped when empty, at most ~5 lines total of actions):
1. 📅 Mùa vụ: up to 2 calendar events in design/launch/push phase or with order-by within 10 days.
2. 🎯 Cơ hội: top 3 POD keywords by opportunity (known competition), not marked listed/skipped, IP not red.
3. 🏈 NFL: top player of the latest fresh week (≥ 85 potential) and the biggest NFL moment of the last 24 h.
4. 🗂 Việc của tôi: "Đang thiết kế" items untouched ≥ 5 days, "Ý tưởng" untouched ≥ 7 days (count + first 2).
5. 🔔 N tin chưa đọc.
Footer: link to the app when `APP_URL` is set. Normal notification (not silent). `make brief-now` previews and sends.
