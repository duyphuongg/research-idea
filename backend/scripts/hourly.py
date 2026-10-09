"""Hourly: NFL trending searches (Khoảnh khắc NFL) + their Telegram alerts. Run by launchd (`make install-hourly`)."""

import asyncio
import logging
import sys
from datetime import datetime

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.models import ScanRun
from app.services.hourly import run_hourly


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    run_id = asyncio.run(run_hourly(session_factory, settings))
    stamp = f"[{datetime.now():%Y-%m-%d %H:%M:%S}]"
    if run_id is None:
        print(f"{stamp} nfl_moments: skipped", flush=True)
        return 0
    with session_factory() as session:
        run = session.get(ScanRun, run_id)
        line = f"{stamp} nfl_moments: {run.status} records={run.records}"
        if run.error:
            line += f" error={run.error.splitlines()[0][:200]}"
    print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
