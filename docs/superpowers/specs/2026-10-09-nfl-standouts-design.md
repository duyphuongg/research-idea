# NFL tuần này — standout players with shirt potential

Date: 2026-10-09. Asked by the user ("cứ làm cho tôi, tôi sẽ thiết kế phù hợp"): which NFL players stood out this
week and have high shirt-selling potential. The user handles design/IP; the page keeps a one-line IP reminder.

## Data

- ESPN public scoreboard JSON `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`
  (optionally `?seasontype=<t>&week=<n>`). Per event: `competitions[0].status.type.name` (`STATUS_FINAL`),
  `competitions[0].leaders` = passingYards / rushingYards / receivingYards leader with `athlete` (id, displayName,
  headshot, jersey, position.abbreviation, team.id, links[0].href) and `displayValue`
  (`"24/42, 316 YDS, 1 TD, 2 INT"`, `"21 CAR, 165 YDS, 1 TD"`, `"9 REC, 130 YDS, 1 TD"`).
- Points (fantasy-style): passing YDS/25 + 4·TD − 2·INT; rushing YDS/10 + 6·TD; receiving YDS/10 + 6·TD + 0.5·REC.
- Demand per player (refreshed at most every 2 days):
  - `etsy_listings`: Etsy `/listings/active?keywords=<name> shirt&limit=1` → `count` (needs ETSY_API_KEY).
  - `merch_suggestions`: Google Suggest for `<name> shirt` → suggestions containing shirt|tee|t-shirt|hoodie|sweatshirt|jersey
    (not "shirtless").
  - `trending`: a google_daily keyword in the last 3 days contains the player's full name (computed at read time).

## Backend

- Tables `nfl_performances` (season, season_type, week, event_id, game, game_date, athlete_id, name, position, jersey,
  team, category, stat_line, points, headshot_url, player_url; unique season/season_type/week/event_id/athlete_id/category)
  and `nfl_player_demand` (athlete_id, date, etsy_listings, merch_suggestions; unique athlete_id/date).
- Job `nfl` (ScanJob, toggle in Settings like other sources): fetch the current scoreboard and the previous week; replace
  rows of each FINAL event; then enrich up to 40 top-point players of those weeks lacking demand in the last 2 days.
  Own ScanRun; network errors → partial/failed, never break the scan.
- `GET /api/nfl/standouts?season=&season_type=&week=` → `{season, season_type, week, weeks: [{season, season_type, week,
  games}], items: [...]}`. Default week = latest stored week with ≥ 10 final games, else the latest stored week.
  Item: `athlete_id, name, position, jersey, team, headshot_url, player_url, games: [str], lines: [{category, stat_line}],
  points, performance (0–1 percentile in the week), etsy_listings, merch_suggestions, trending, potential (0–100)`.
  `potential = 100 · (0.5·performance + 0.3·min(merch_suggestions/10, 1) + 0.2·min(log10(etsy_listings+1)/4, 1))
  + 10 if trending`, capped at 100; unknown demand counts as 0. Sorted by potential desc.

## Frontend

`/nfl` "NFL tuần này": week selector, card grid (headshot, name, team · position #jersey, stat lines, points, potential bar,
Etsy listings, Google merch suggestions, 🔥 Đang trend), links: ESPN ↗, Etsy search "<name> shirt" ↗, Phân tích ngách.
One-line note: player names/numbers/likeness and team logos are licensed — use as inspiration. Nav entry.

## Testing

Parser and points unit tests from a trimmed ESPN fixture; job with respx (ESPN, Etsy, Google — never real network);
service/API tests; frontend lint + build + manual check.
