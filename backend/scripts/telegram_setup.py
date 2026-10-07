"""Interactive Telegram setup: verifies the bot, finds your chat id, writes backend/.env, sends a test message.

Run via `make telegram-setup`. The bot token is never printed.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from getpass import getpass
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.notify.telegram import API, TelegramError, send_text  # noqa: E402

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
TAILSCALE_APP = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def api_get(token: str, method: str) -> dict | None:
    try:
        resp = httpx.get(f"{API}/bot{token}/{method}", timeout=20)
        data = resp.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        return None
    return data if resp.status_code == 200 and data.get("ok") else None


def latest_private_chat_id(updates: list[dict]) -> int | None:
    for update in reversed(updates):
        chat = (update.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            return chat["id"]
    return None


def default_app_url() -> str | None:
    exe = shutil.which("tailscale") or TAILSCALE_APP
    try:
        out = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=10).stdout
        name = json.loads(out)["Self"]["DNSName"].rstrip(".")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError):
        return None
    return f"http://{name}:3737" if name else None


def update_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    remaining = dict(values)
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if "=" in line and key in values:
            if key in remaining:  # first occurrence is replaced; later duplicates are dropped
                out.append(f"{key}={remaining.pop(key)}")
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in remaining.items()]
    path.write_text("\n".join(out) + "\n")
    os.chmod(path, 0o600)


def main() -> int:
    token = getpass("Bot token (từ @BotFather): ").strip()
    me = api_get(token, "getMe")
    if not me:
        print("Token không đúng")
        return 1
    username = me["result"]["username"]
    print(f"Bot: @{username}")

    updates = api_get(token, "getUpdates")
    chat_id = latest_private_chat_id(updates["result"]) if updates else None
    if chat_id is None:
        print(f"Hãy mở Telegram, gửi 1 tin bất kỳ cho bot @{username} rồi chạy lại.")
        return 1

    default = default_app_url()
    prompt = f"APP_URL [{default}]: " if default else "APP_URL (vd http://may-cua-ban.ts.net:3737): "
    app_url = input(prompt).strip() or default or ""

    values = {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_CHAT_ID": str(chat_id)}
    if app_url:
        values["APP_URL"] = app_url
    update_env(ENV_PATH, values)

    settings = Settings(_env_file=None, telegram_bot_token=token, telegram_chat_id=str(chat_id))
    try:
        asyncio.run(send_text(settings, "✅ POD Trend Radar đã kết nối. Bạn sẽ nhận tin sau mỗi lần quét (8:00 và 20:00)."))
    except TelegramError as exc:
        print(f"Đã lưu vào backend/.env nhưng gửi tin thử lỗi: {exc}")
        return 1
    print("Đã lưu vào backend/.env và gửi tin thử.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
