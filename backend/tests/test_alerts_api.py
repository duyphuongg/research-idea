from datetime import date, datetime

from app.models import Alert


def _add(session, i, read=False):
    session.add(Alert(kind="niche", subject_id=i, level=1, priority=60, title=f"n{i}", reason="Điểm 60",
                      link=f"/trends/{i}", scan_date=date(2026, 10, 8),
                      created_at=datetime(2026, 10, 8, 1, i), read_at=datetime(2026, 10, 8) if read else None))
    session.commit()


def test_list_and_mark_read(client, session):
    _add(session, 1, read=True)
    _add(session, 2)
    r = client.get("/api/alerts").json()
    assert r["unread"] == 1 and [i["title"] for i in r["items"]] == ["n2", "n1"]
    assert r["items"][0]["read"] is False
    assert client.get("/api/alerts/unread-count").json() == {"unread": 1}
    assert client.post("/api/alerts/read").json() == {"unread": 0}
    assert client.get("/api/alerts/unread-count").json() == {"unread": 0}


def test_telegram_status_has_no_secret(client):
    body = client.get("/api/alerts/telegram").json()
    assert body == {"configured": False, "app_url": None}


def test_test_message_unconfigured(client):
    r = client.post("/api/alerts/test")
    assert r.status_code == 400 and "make telegram-setup" in r.json()["detail"]


def test_test_message_telegram_error(client, monkeypatch):
    from app.api import alerts as mod
    from app.notify.telegram import TelegramError

    async def boom(settings, text, *, client=None):
        raise TelegramError("Telegram trả về HTTP 401")

    client.app.state.settings = client.app.state.settings.model_copy(
        update={"telegram_bot_token": "SECRET", "telegram_chat_id": "42"})
    monkeypatch.setattr(mod, "send_text", boom)
    r = client.post("/api/alerts/test")
    assert r.status_code == 502 and "SECRET" not in r.text and "401" in r.json()["detail"]
    body = client.get("/api/alerts/telegram").json()
    assert body == {"configured": True, "app_url": None}
