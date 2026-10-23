---
name: preview-on-db-copy
description: Run the working tree (backend + Next dev UI) against a fresh copy of the real radar.db on ports 8091/3091, to check a change on real data in the browser or to run analysis scripts on real data — without touching the live app (:3737/:8020), the real DB, Telegram or Etsy. Use before reporting UI work done, when comparing old vs new scoring on real data, or when the user asks to preview/try a change.
---

# Preview on a DB copy

The live app (`make up`, UI :3737, API :8020) and `backend/data/radar.db` are in daily use. Preview here instead.

## Start
```bash
.claude/skills/preview-on-db-copy/start.sh          # reuses an existing copy
.claude/skills/preview-on-db-copy/start.sh --fresh  # re-copies the real DB first (after a scan, or to reset)
```
It copies the DB with `sqlite3 .backup` into `$TMPDIR/pod-trend-preview/radar-copy.db`, runs `alembic upgrade head` on the
copy, and starts the API on :8091 and `next dev` on :3091 (Telegram and Etsy keys blanked, scheduler off). The backend
has no `--reload`: rerun `start.sh` after backend changes. The frontend hot-reloads.

## Check
- Open `http://localhost:3091/<page>` with the chrome-devtools MCP tools; screenshot desktop (1440×900) and mobile
  (`emulate` viewport `390x844x2,mobile,touch`). Check for horizontal overflow with
  `document.documentElement.scrollWidth`.
- The first load of a page compiles (can take a minute after other dev servers or a cold cache); warm it with
  `curl -s -m 120 -o /dev/null localhost:3091/<page>` before screenshotting. If a screenshot is blank, take it again.
- Run `start.sh` directly, not piped into `tail`/`head`.
- API directly: `curl -s localhost:8091/api/...`.
- Scripts on real data: `DATABASE_URL=sqlite:///$TMPDIR/pod-trend-preview/radar-copy.db uv run python <script>`
  from `backend/` (put scripts in the scratchpad, not the repo). Stored derived columns (e.g. new signal fields) stay
  empty until a scan runs; backfill them on the copy only.

## Stop
```bash
.claude/skills/preview-on-db-copy/stop.sh
```
Always stop the servers when done. Report what you checked and on which data date; say plainly that the live app and
real DB were not changed.
