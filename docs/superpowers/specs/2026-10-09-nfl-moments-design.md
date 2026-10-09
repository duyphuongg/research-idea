# Khoảnh khắc NFL — hourly trending NFL searches

Date: 2026-10-09. User: controversial moments / players topping US searches are a good shirt niche; scan hourly.

## Data

- Google Trends RSS `https://trends.google.com/trending/rss?geo=US`: ~10 latest trends, each with `title`,
  `ht:approx_traffic` ("10000+"), `pubDate`, `ht:picture`, up to 3 `ht:news_item` (title, url, source).
- ESPN teams `.../nfl/teams` (32) and rosters `.../nfl/teams/{id}/roster` (~80 players each, all position groups),
  refreshed when older than 7 days → table `nfl_players` (athlete_id, name, first_name, last_name, team, position,
  jersey, headshot_url, updated_on).

## Matching a trend to NFL

Normalize text: lowercase, drop punctuation and suffixes jr/sr/ii/iii/iv, singularize tokens.
- Player: some adjacent token pair (a, b) in the query has b == player's last name and a == first name, or a shares
  its first letter with the first name ("cd lamb" → CeeDee Lamb). Exact first-name matches win; several equal
  candidates → no match.
- Team: query contains a team nickname ("cowboys") or full name, and (for nicknames shared with other leagues:
  cardinals, giants, jets? — simply always) a news title mentions NFL/football/quarterback/touchdown/coach.
- Else: a news title contains "NFL".
Unmatched trends are ignored.

## Storage and job

Table `nfl_moments`: id, query (unique), traffic (max seen), first_seen, last_seen, news (JSON ≤ 3), picture_url,
athlete_id, team, etsy_listings. Job `nfl_moments` (script `backend/scripts/nfl_moments.py`, launchd
`io.podtrendradar.hourly` at minute 30 every hour, `make install-hourly`): refresh rosters if stale, fetch RSS, upsert
matches, Etsy count for "<query> shirt" on first sight (when ETSY_API_KEY), detect moment alerts, send Telegram
(quiet hours still apply). Own ScanRun `nfl_moments`.

## Alerts

Kind `nfl_moment` 🗯️ "Khoảnh khắc NFL", bell on. Moment with traffic ≥ `nfl_moment_min_traffic` (20000) first seen
in the last 2 days; at most `nfl_moment_max_per_day` (2) per day; once per moment. Title = query; reason =
"20.000+ lượt tìm · <first news title>"; image = picture or player headshot; external_url = first news url; link `/nfl`.
Also checked by the regular scan.

## Fix

`standouts.trending` = the player has an `nfl_moments` row in the last 3 days (replaces the full-name substring check).

## API / UI

`GET /api/nfl/moments?days=7` → `{items: [{id, query, traffic, first_seen, last_seen, news: [{title, url, source}],
picture_url, etsy_listings, team, player: {athlete_id, name, team, position, headshot_url} | null}]}` sorted by traffic
desc. `/nfl` gets a "Khoảnh khắc đang hot" section above the players.
