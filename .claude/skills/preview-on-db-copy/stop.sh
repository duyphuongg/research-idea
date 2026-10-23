#!/usr/bin/env bash
# Stop the preview servers started by start.sh (the DB copy is kept for the next run).
API_PORT=${API_PORT:-8091}
UI_PORT=${UI_PORT:-3091}
for port in "$API_PORT" "$UI_PORT"; do
  pids=$(lsof -ti tcp:"$port" 2>/dev/null)
  [ -n "$pids" ] && kill $pids && echo "Stopped :$port"
done
exit 0
