from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.config import Settings
from app.analysis.alerts import AlertsConfig
from app.models import Alert
from app.notify.telegram import format_caption, send_pending

NOW = datetime(2026, 10, 8, 13, 0)
TOKEN = "123:secret"
BASE = f"https://api.telegram.org/bot{TOKEN}"


def _settings(**kw):
    return Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42",
                    app_url="http://mac.ts.net:3737", **kw)


def _alert(session, i, kind="listing", level=1, priority=1.0, image=True, created=NOW):
    a = Alert(kind=kind, subject_id=i, level=level, priority=priority, title=f"Tee <{i}>", reason="+5 lượt lưu/ngày",
              image_url=f"https://img/{i}.jpg" if image else None, link=f"/signals?x={i}",
              external_url=f"https://www.etsy.com/listing/{i}", watch_keyword="game day",
              scan_date=NOW.date(), created_at=created)
    session.add(a)
    session.flush()
    return a


def test_caption():
    a = Alert(kind="listing", subject_id=1, level=2, priority=1, title="A & B", reason="Super Breakout",
              image_url=None, link="/signals", external_url="https://www.etsy.com/listing/1",
              watch_keyword="pickleball", scan_date=NOW.date())
    text = format_caption(a, "http://mac:3737")
    assert text.startswith("🔥 <b>Etsy bứt phá</b> · pickleball\nA &amp; B\nSuper Breakout\n")
    assert '<a href="http://mac:3737/signals">Mở trong app</a>' in text
    assert '<a href="https://www.etsy.com/listing/1">Etsy</a>' in text


async def test_not_configured_sends_nothing(session):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        n = await send_pending(session, Settings(_env_file=None), now=NOW)
    assert n == 0 and not mock.calls


async def test_sends_top_items_and_summary(session):
    for i in range(7):
        _alert(session, i, priority=float(i))
    _alert(session, 99, created=NOW - timedelta(days=3))  # too old, ignored
    with respx.mock() as mock:
        photo = mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(200, json={"ok": True}))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        n = await send_pending(session, _settings(), AlertsConfig(telegram_max_items=5), now=NOW)
    assert n == 7
    assert photo.call_count == 5 and msg.call_count == 1
    assert "và 2 tin khác" in msg.calls[0].request.content.decode()
    assert all(a.sent_at is not None for a in session.query(Alert).filter(Alert.subject_id < 99))


async def test_failure_keeps_unsent_and_429_stops(session, caplog):
    _alert(session, 1, priority=3)
    _alert(session, 2, priority=2)
    _alert(session, 3, priority=1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(side_effect=[
            httpx.Response(500), httpx.Response(429), httpx.Response(200, json={"ok": True}),
        ])
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 0
    assert all(a.sent_at is None for a in session.query(Alert))
    assert TOKEN not in caplog.text


async def test_bad_photo_falls_back_to_text(session):
    _alert(session, 1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(400))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 1 and msg.call_count == 1


async def test_token_never_logged_by_httpx(session, caplog):
    import logging
    _alert(session, 1)
    caplog.set_level(logging.DEBUG)
    # real httpx client (respx patches the transport), so httpx's own request logging runs
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(200, json={"ok": True}))
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 1
    assert TOKEN not in caplog.text


def test_caption_truncates_fields_before_escaping():
    a = Alert(kind="listing", subject_id=1, level=1, priority=1, title="&" * 900, reason="<" * 900,
              image_url=None, link="/signals", external_url="https://www.etsy.com/listing/1",
              watch_keyword="pickleball", scan_date=NOW.date())
    text = format_caption(a, "http://mac:3737")
    import html as _html
    import re
    assert len(_html.unescape(re.sub(r"<[^>]+>", "", text))) <= 1024  # Telegram counts the parsed text
    assert text.count("&amp;") == 200 and text.count("&lt;") == 300
    assert text.endswith('<a href="https://www.etsy.com/listing/1">Etsy</a>')


async def test_unexpected_error_skips_one_alert_and_keeps_others(session):
    _alert(session, 1, priority=3)
    _alert(session, 2, priority=2)
    _alert(session, 3, priority=1)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(side_effect=[
            httpx.Response(200, json={"ok": True}), RuntimeError("weird"), httpx.Response(200, json={"ok": True}),
        ])
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 2
    assert sorted(a.subject_id for a in session.query(Alert) if a.sent_at) == [1, 3]


async def test_transport_error_stops_the_run(session):
    for i in range(3):
        _alert(session, i, priority=float(10 - i))
    with respx.mock() as mock:
        photo = mock.post(f"{BASE}/sendPhoto").mock(side_effect=httpx.ConnectTimeout("slow"))
        n = await send_pending(session, _settings(), now=NOW)
    assert n == 0 and photo.call_count == 1
    assert all(a.sent_at is None for a in session.query(Alert))


async def test_summary_escapes_app_url(session):
    for i in range(2):
        _alert(session, i)
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(200, json={"ok": True}))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        await send_pending(session, Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42", app_url="http://h/?a=1&b=<2>"), AlertsConfig(telegram_max_items=1), now=NOW)
    body = msg.calls[0].request.content.decode()
    assert "a=1&amp;b=&lt;2&gt;/alerts" in body
