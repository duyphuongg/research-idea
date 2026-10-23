#!/usr/bin/env bash
# Start a preview of the working tree on a fresh copy of the real DB (never the live app or DB).
#   start.sh            copy the DB (unless a copy exists), migrate the copy, start API :8091 + UI :3091
#   start.sh --fresh    re-copy the DB first
# Env overrides: PREVIEW_DIR (default $TMPDIR/pod-trend-preview), API_PORT (8091), UI_PORT (3091).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
TMP=${TMPDIR:-/tmp}
DIR=${PREVIEW_DIR:-${TMP%/}/pod-trend-preview}
DIR=${DIR%/}
API_PORT=${API_PORT:-8091}
UI_PORT=${UI_PORT:-3091}
DB="$DIR/radar-copy.db"

for port in "$API_PORT" "$UI_PORT"; do
  if [ "$port" = 8020 ] || [ "$port" = 3737 ]; then echo "Refusing to use the live app's port $port" >&2; exit 1; fi
done

mkdir -p "$DIR"
if [ "${1:-}" = "--fresh" ] || [ ! -f "$DB" ]; then
  # sqlite3 .backup takes a consistent snapshot even while a scan is writing.
  sqlite3 "$ROOT/backend/data/radar.db" ".backup '$DB'"
  echo "Copied real DB -> $DB"
fi

# Everything below points at the copy; Telegram and Etsy are disabled so nothing leaves the machine.
export DATABASE_URL="sqlite:///$DB" SCHEDULER_ENABLED=false TELEGRAM_BOT_TOKEN= TELEGRAM_CHAT_ID= ETSY_API_KEY=
(cd "$ROOT/backend" && .venv/bin/alembic upgrade head 2>&1 | grep -E "Running upgrade|ERROR" || true)

lsof -ti tcp:"$API_PORT" >/dev/null 2>&1 && kill $(lsof -ti tcp:"$API_PORT") 2>/dev/null || true
(cd "$ROOT/backend" && nohup .venv/bin/uvicorn --factory app.main:create_app --port "$API_PORT" \
  > "$DIR/backend.log" 2>&1 < /dev/null &)

if ! lsof -ti tcp:"$UI_PORT" >/dev/null 2>&1; then
  (cd "$ROOT/frontend" && BACKEND_URL="http://127.0.0.1:$API_PORT" nohup npx next dev --port "$UI_PORT" \
    > "$DIR/frontend.log" 2>&1 < /dev/null &)
fi

for _ in $(seq 1 60); do
  curl -s -m 2 -o /dev/null "localhost:$API_PORT/api/ping" && curl -s -m 5 -o /dev/null "localhost:$UI_PORT" && break
  sleep 1
done
echo "Preview: http://localhost:$UI_PORT  (API :$API_PORT, DB $DB, logs in $DIR)"
