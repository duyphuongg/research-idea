"""Hourly (minute 15): big sports events (World Series, NBA Finals, …) → 🏆 Telegram. Run by launchd (`make install-events`)."""

import asyncio
import logging
import sys
from datetime import datetime

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.services.events_watch import run_events


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    new = asyncio.run(run_events(make_session_factory(make_engine(settings.database_url)), settings))
    for alert in new or []:  # quiet when nothing happened: this runs every hour
        state = "sent" if alert["sent"] else "held"
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 🏆 {alert['title']} — {alert['reason']} ({state})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
