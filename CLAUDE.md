# POD Trend Radar

Niche and best-seller research app for a TikTok Shop US print-on-demand seller (t-shirts, sweatshirts, hoodies).
Etsy-focused (Amazon was removed; `amazon_ranks` is kept as history only). The user reads Vietnamese: all UI copy,
Telegram messages and `backend/config/*.yaml` comments are Vietnamese; code, comments and docs are English.

## Layout
- `backend/` — FastAPI + SQLAlchemy 2 + Alembic, SQLite at `backend/data/radar.db` (real, ~100MB, gitignored).
  - `app/analysis/` pure logic (scoring, signals, momentum, topics, IP check) — unit-tested without a DB.
  - `app/services/` DB queries + composition; `app/pipeline/` scans and jobs; `app/api/` routers; `app/notify/` Telegram.
  - `config/*.yaml` user-tunable thresholds (alerts, listing signals, topics, IP terms, events). Prefer adding a
    knob there over hard-coding a number.
  - `scripts/` entry points run by launchd (daily scan 08:00/20:00, hourly NFL moments, events, morning brief).
- `frontend/` — Next.js 16 + React 19 + Tailwind 4. Read `frontend/AGENTS.md`: this Next version differs from what
  you know. "Press Room" design system: tokens in `app/globals.css`, primitives in `components/ui/`.
- `docs/superpowers/specs/` — one design doc per feature (`YYYY-MM-DD-<topic>-design.md`), written before coding.

## Commands
- Tests: `cd backend && uv run pytest -q` (whole suite ~3s). Frontend: `cd frontend && npx tsc --noEmit -p . && npm run lint`.
- New migration: add a file under `backend/alembic/versions/` chained to the current head; `test_migrations.py`
  checks every model table exists after `upgrade head`.
- Preview a change on real data: use the `preview-on-db-copy` skill (never the live app).

## The live app — do not disturb
- `make up` serves the production build on UI :3737 / API :8020 (reached remotely via Tailscale) and launchd jobs
  write to `backend/data/radar.db` on a schedule. Telegram (`backend/.env`) sends to the user's phone.
- Never write to `backend/data/radar.db` directly, and never run `alembic upgrade` against it — copy it first
  (the preview skill does this). Applying migrations to the real DB is `make migrate`, only when the user asks.
- Never run `next build` / `npm run build` in `frontend/`: it overwrites `.next`, which the running :3737 server
  serves. `make up` rebuilds when sources changed.
- A PreToolUse hook (`.claude/hooks/guard-live.sh`) blocks these; don't work around it.
- Commit only when the user asks; they deploy with `make migrate && make down && make up`.

## Conventions
- Match the surrounding code: dataclasses for pure results, `Literal` sort keys, small helpers over abstractions.
- Tests use in-memory SQLite fixtures from `backend/tests/conftest.py`; Telegram is stubbed automatically.
- Missing data shows as `—`, never 0. Estimates (views, revenue) are labelled as estimates.
