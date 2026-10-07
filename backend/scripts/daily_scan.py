"""Run one full scan of every enabled source, print a summary and exit.

Used by the launchd daily job (`make install-daily`); also `make scan-now`.
"""

import asyncio
import logging
import sys
from datetime import datetime

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import ScanRun
from app.services.daily import run_daily_scan


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] daily scan done", flush=True)
    return 1 if runs and all(run.status == "failed" for run in runs) else 0


if __name__ == "__main__":
    sys.exit(main())
