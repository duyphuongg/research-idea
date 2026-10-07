"""Build this week's Telegram digest now: print a plain-text preview and send it if Telegram is configured.

Run via `make digest-now`. Does not change the weekly schedule (digest_last_week). Never prints the token.
"""

import asyncio
import html
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.notify.telegram import TelegramError, send_text, telegram_configured  # noqa: E402
from app.services.digest import build_digest  # noqa: E402


def plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text))


async def main() -> int:
    settings = get_settings()
    session_factory = make_session_factory(make_engine(settings.database_url))
    with session_factory() as session:
        text = build_digest(session, datetime.now().astimezone().date(), settings.app_url)
    print(plain(text))
    print()
    if not telegram_configured(settings):
        print("Telegram chưa được cấu hình (make telegram-setup) — chỉ xem trước, không gửi.")
        return 0
    try:
        await send_text(settings, text)
    except TelegramError as exc:
        print(f"Gửi thất bại: {exc}")
        return 1
    print("Đã gửi tin tổng kết.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
