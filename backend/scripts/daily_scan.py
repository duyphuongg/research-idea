"""Run one full scan of every enabled source, back up the database, print a summary and exit.

Used by the launchd daily job (`make install-daily`); also `make scan-now`.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import ScanRun
from app.services.backup import backup_database, sqlite_path
from app.services.daily import run_daily_scan

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    if "--backup-only" in sys.argv[1:]:
        backup(settings)
        return 0
    session_factory = make_session_factory(make_engine(settings.database_url))
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] daily scan start", flush=True)
    run_ids = asyncio.run(run_daily_scan(session_factory, settings))
    if run_ids is None:
        print("skipped: another scan is running", flush=True)
        return 0
    with session_factory() as session:
        runs = [session.get(ScanRun, run_id) for run_id in run_ids]
    for run in runs:
        line = f"  {run.source}: {run.status} records={run.records}"
        if run.error:
            line += f" error={run.error.splitlines()[0][:200]}"
        print(line, flush=True)
    backup(settings)
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] daily scan done", flush=True)
    return 1 if runs and all(run.status == "failed" for run in runs) else 0


def backup(settings) -> None:
    db = sqlite_path(settings.database_url, BACKEND_DIR)
    if db is None or not db.exists():
        return
    try:
        dest = Path(settings.backup_dir).expanduser()
        out = backup_database(db, dest if dest.is_absolute() else BACKEND_DIR / dest, keep=settings.backup_keep)
        print(f"  backup: {out}", flush=True)
    except Exception as exc:  # a failed backup must not fail the scan
        print(f"  backup failed: {type(exc).__name__}: {exc}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
