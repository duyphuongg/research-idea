#!/usr/bin/env bash
# PreToolUse(Bash) guard for the live app: blocks commands that would write to the real DB or
# overwrite the production build that `make up` serves. Exit 2 = block, stderr goes back to Claude.
set -u

cmd=$(jq -r '.tool_input.command // ""')
lower=$(printf '%s' "$cmd" | tr '[:upper:]' '[:lower:]')

block() {
  printf 'Blocked by .claude/hooks/guard-live.sh: %s\n' "$1" >&2
  exit 2
}

# The real database: backend/data/radar.db (copies such as radar-copy.db are fine).
real_db='data/radar\.db([^a-z0-9_-]|$)'

# 1. SQL writes to the real DB through sqlite3.
if printf '%s' "$lower" | grep -Eq 'sqlite3' && printf '%s' "$lower" | grep -Eq "$real_db" \
  && printf '%s' "$lower" | grep -Eq '\b(insert|update|delete|drop|alter|create|replace|vacuum|attach)\b'; then
  block "SQL write to backend/data/radar.db. Copy it first (preview-on-db-copy skill) and work on the copy."
fi

# 2. Alembic migrations not pointed at another database (`make migrate` stays the user's explicit path).
if printf '%s' "$lower" | grep -Eq 'alembic[^|;&]*\b(upgrade|downgrade|stamp)\b'; then
  if ! printf '%s' "$cmd" | grep -Eq 'DATABASE_URL=' || printf '%s' "$lower" | grep -Eq "database_url=[^ ]*$real_db"; then
    block "alembic would migrate the real DB. Set DATABASE_URL=sqlite:///<copy> or ask the user to run make migrate."
  fi
fi

# 3. Production builds overwrite frontend/.next, which the live :3737 server is serving.
if printf '%s' "$lower" | grep -Eq '(next build|npm run build|npm build)'; then
  block "a frontend build overwrites .next used by the live app on :3737. Type-check with 'npx tsc --noEmit -p .' and 'npm run lint'; make up rebuilds when needed."
fi

exit 0
