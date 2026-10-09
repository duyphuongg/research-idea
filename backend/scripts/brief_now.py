"""Preview the morning brief ("Hôm nay làm gì"); with --send also send it to Telegram (`make brief-now SEND=1`)."""

import asyncio
import sys
from datetime import datetime

from app.config import get_settings
from app.db import make_engine, make_session_factory
from app.notify.telegram import send_text
from app.services.brief import build_brief


def main() -> int:
    settings = get_settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    with session_factory() as session:
        text = build_brief(session, datetime.now().astimezone().date(), settings.app_url)
    print(text or "(không có gì để báo hôm nay)")
    if text and "--send" in sys.argv[1:]:
        asyncio.run(send_text(settings, text))
        print("→ đã gửi Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
