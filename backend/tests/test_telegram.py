import html as _html
import json
import logging
import re
from datetime import datetime, timedelta

import httpx
import pytest
import respx

from app.analysis.alerts import AlertsConfig
from app.config import Settings
from app.models import Alert
from app.notify.telegram import send_pending

NOW = datetime(2026, 10, 8, 13, 0)
LOCAL = datetime(2026, 10, 8, 8, 5)  # morning scan, outside quiet hours
QUIET = datetime(2026, 10, 8, 23, 0)
TOKEN = "123:secret"
BASE = f"https://api.telegram.org/bot{TOKEN}"
OK = httpx.Response(200, json={"ok": True})


def _settings(**kw):
    kw.setdefault("app_url", "http://mac.ts.net:3737")
    return Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42", **kw)


def _alert(session, i, kind="listing", level=1, priority=1.0, image=True, created=NOW,
           title=None, reason="+5 lượt lưu/ngày"):
    a = Alert(kind=kind, subject_id=i, level=level, priority=priority, title=title or f"Tee {i}", reason=reason,
              image_url=f"https://img/{i}.jpg" if image else None, link=f"/signals?x={i}",
              external_url=f"https://www.etsy.com/listing/{i}", watch_keyword="game day",
              scan_date=NOW.date(), created_at=created)
    session.add(a)
    session.flush()
    return a


def _body(call) -> dict:
    return json.loads(call.request.content.decode())


def _visible(text: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", text))


def _routes(mock):
    return (mock.post(f"{BASE}/sendMediaGroup").mock(return_value=OK),
            mock.post(f"{BASE}/sendPhoto").mock(return_value=OK),
            mock.post(f"{BASE}/sendMessage").mock(return_value=OK))


async def test_not_configured_sends_nothing(session):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        n = await send_pending(session, Settings(_env_file=None), now=NOW, local_now=LOCAL)
    assert n == 0 and not mock.calls


async def test_one_album_for_the_whole_scan(session):
    for i in range(7):
        _alert(session, i, priority=float(10 - i), image=i not in (1, 3))  # top 5 has 3 images
    _alert(session, 99, created=NOW - timedelta(days=3))  # too old, ignored
    with respx.mock(assert_all_called=False) as mock:
        album, photo, msg = _routes(mock)
        n = await send_pending(session, _settings(), AlertsConfig(telegram_max_items=5), now=NOW, local_now=LOCAL)
    assert n == 7
    assert album.call_count == 1 and photo.call_count == 0 and msg.call_count == 0
    media = _body(album.calls[0])["media"]
    assert [m["media"] for m in media] == ["https://img/0.jpg", "https://img/2.jpg", "https://img/4.jpg"]
    assert all(m["type"] == "photo" for m in media)
    assert "caption" in media[0] and media[0]["parse_mode"] == "HTML"
    assert all("caption" not in m for m in media[1:])
    caption = media[0]["caption"]
    assert "7 tin mới" in caption
    assert all(f"{k}. " in caption for k in range(1, 6)) and "6. " not in caption
    assert "… và 2 tin khác" in caption
    assert '<a href="http://mac.ts.net:3737/alerts">xem tất cả</a>' in caption
    assert all(a.sent_at == NOW for a in session.query(Alert).filter(Alert.subject_id < 99))
    assert session.query(Alert).filter(Alert.subject_id == 99).one().sent_at is None


async def test_album_with_five_photos(session):
    for i in range(7):
        _alert(session, i, priority=float(10 - i))
    with respx.mock(assert_all_called=False) as mock:
        album, photo, msg = _routes(mock)
        n = await send_pending(session, _settings(), AlertsConfig(telegram_max_items=5), now=NOW, local_now=LOCAL)
    assert n == 7 and album.call_count == 1 and photo.call_count == 0 and msg.call_count == 0
    media = _body(album.calls[0])["media"]
    assert len(media) == 5
    assert "caption" in media[0] and all("caption" not in m for m in media[1:])
    caption = media[0]["caption"]
    assert "7 tin mới" in caption and "… và 2 tin khác" in caption
    assert all(f"{k}. " in caption for k in range(1, 6))


async def test_caption_format(session):
    _alert(session, 1, level=2, title="A & B", reason="Super Breakout", image=False)
    with respx.mock(assert_all_called=False) as mock:
        _, _, msg = _routes(mock)
        await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    text = _body(msg.calls[0])["text"]
    assert text == ('🔔 <b>1 tin mới</b>\n1. 🔥 <b>Etsy bứt phá</b> · game day\n'
                    '<a href="http://mac.ts.net:3737/signals?x=1">A &amp; B</a> — Super Breakout')


async def test_no_app_url_plain_title_and_no_view_all_link(session):
    for i in range(3):
        _alert(session, i, priority=float(10 - i), image=False)
    with respx.mock(assert_all_called=False) as mock:
        _, _, msg = _routes(mock)
        await send_pending(session, _settings(app_url=None), AlertsConfig(telegram_max_items=1),
                           now=NOW, local_now=LOCAL)
    text = _body(msg.calls[0])["text"]
    assert "<a " not in text
    assert "\nTee 0 — +5 lượt lưu/ngày" in text
    assert text.endswith("… và 2 tin khác")


@pytest.mark.parametrize("kinds,silent", [
    ([("hot_product", 1), ("listing", 1)], True),
    ([("hot_product", 1), ("niche", 1)], False),
    ([("hot_product", 1), ("listing", 2)], False),
])
async def test_silent_unless_high_priority(session, kinds, silent):
    for i, (kind, level) in enumerate(kinds):
        _alert(session, i, kind=kind, level=level)
    with respx.mock(assert_all_called=False) as mock:
        album, _, _ = _routes(mock)
        await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert _body(album.calls[0])["disable_notification"] is silent


async def test_high_priority_beyond_the_listed_items_still_loud(session):
    for i in range(3):
        _alert(session, i, kind="hot_product", priority=float(10 - i), image=False)
    _alert(session, 9, kind="niche", image=False)  # ranked before hot products
    with respx.mock(assert_all_called=False) as mock:
        _, _, msg = _routes(mock)
        await send_pending(session, _settings(), AlertsConfig(telegram_max_items=1), now=NOW, local_now=LOCAL)
    assert _body(msg.calls[0])["disable_notification"] is False


async def test_one_image_sends_photo(session):
    _alert(session, 1)
    _alert(session, 2, image=False, priority=0)
    with respx.mock(assert_all_called=False) as mock:
        album, photo, msg = _routes(mock)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == 2 and photo.call_count == 1 and album.call_count == 0 and msg.call_count == 0
    body = _body(photo.calls[0])
    assert body["photo"] == "https://img/1.jpg" and body["parse_mode"] == "HTML"
    assert "2 tin mới" in body["caption"] and body["disable_notification"] is True


async def test_no_images_sends_message(session):
    _alert(session, 1, image=False)
    _alert(session, 2, image=False)
    with respx.mock(assert_all_called=False) as mock:
        album, photo, msg = _routes(mock)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == 2 and msg.call_count == 1 and album.call_count == 0 and photo.call_count == 0
    body = _body(msg.calls[0])
    assert "2 tin mới" in body["text"] and body["disable_web_page_preview"] is True
    assert body["disable_notification"] is True


@pytest.mark.parametrize("images", [1, 3])
async def test_bad_image_falls_back_to_one_message(session, images):
    for i in range(images):
        _alert(session, i, priority=float(10 - i))
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{BASE}/sendMediaGroup").mock(return_value=httpx.Response(400))
        mock.post(f"{BASE}/sendPhoto").mock(return_value=httpx.Response(400))
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=OK)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == images and msg.call_count == 1
    assert f"{images} tin mới" in _body(msg.calls[0])["text"]
    assert all(a.sent_at == NOW for a in session.query(Alert))


@pytest.mark.parametrize("local", [QUIET, datetime(2026, 10, 8, 6, 59), datetime(2026, 10, 8, 22, 0)])
async def test_quiet_hours_hold_everything(session, local):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        n = await send_pending(session, _settings(), now=NOW, local_now=local)
    assert n == 0 and not mock.calls
    assert session.query(Alert).one().sent_at is None


async def test_quiet_hours_end_at_seven(session):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        _, photo, _ = _routes(mock)
        n = await send_pending(session, _settings(), now=NOW, local_now=datetime(2026, 10, 8, 7, 0))
    assert n == 1 and photo.call_count == 1


async def test_equal_quiet_bounds_disable_quiet_hours(session):
    _alert(session, 1)
    with respx.mock(assert_all_called=False) as mock:
        _, photo, _ = _routes(mock)
        n = await send_pending(session, _settings(), AlertsConfig(quiet_start=0, quiet_end=0),
                               now=NOW, local_now=QUIET)
    assert n == 1 and photo.call_count == 1


async def test_daytime_quiet_window(session):
    _alert(session, 1)
    cfg = AlertsConfig(quiet_start=12, quiet_end=14)
    with respx.mock(assert_all_called=False) as mock:
        n = await send_pending(session, _settings(), cfg, now=NOW, local_now=datetime(2026, 10, 8, 13, 0))
    assert n == 0 and not mock.calls
    with respx.mock(assert_all_called=False) as mock:
        _, photo, _ = _routes(mock)
        n = await send_pending(session, _settings(), cfg, now=NOW, local_now=QUIET)
    assert n == 1


@pytest.mark.parametrize("outcome", [httpx.Response(429), httpx.Response(500), httpx.ConnectTimeout("slow"),
                                     RuntimeError("weird")])
async def test_failure_marks_nothing(session, caplog, outcome):
    for i in range(3):
        _alert(session, i, priority=float(10 - i))
    with respx.mock(assert_all_called=False) as mock:
        album = mock.post(f"{BASE}/sendMediaGroup").mock(side_effect=[outcome])
        msg = mock.post(f"{BASE}/sendMessage").mock(return_value=OK)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == 0 and album.call_count == 1 and msg.call_count == 0
    assert all(a.sent_at is None for a in session.query(Alert))
    assert TOKEN not in caplog.text


async def test_caption_fits_telegram_limit(session):
    for i in range(5):
        _alert(session, i, priority=float(10 - i), title=f"{i} A&B <tee> " + "x" * 300,
               reason="R&D <ok> " + "y" * 300)
    with respx.mock(assert_all_called=False) as mock:
        album, _, _ = _routes(mock)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == 5
    media = _body(album.calls[0])["media"]
    caption = media[0]["caption"]
    assert len(_visible(caption)) <= 1024
    assert "5 tin mới" in caption and "A&amp;B &lt;tee&gt;" in caption and "R&amp;D &lt;ok&gt;" in caption
    assert "<tee>" not in caption
    listed = len(re.findall(r"^\d+\. ", _visible(caption), flags=re.M))
    assert listed < 5 and f"… và {5 - listed} tin khác" in caption
    assert len(media) == listed
    assert all(a.sent_at == NOW for a in session.query(Alert))


def _u16(text: str) -> int:
    return len(_visible(text).encode("utf-16-le")) // 2


async def test_caption_counts_utf16_units(session):
    for i in range(5):
        _alert(session, i, priority=float(10 - i), title="🔥" * 90, reason="🎃" * 120)
    with respx.mock(assert_all_called=False) as mock:
        album, _, _ = _routes(mock)
        await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    caption = _body(album.calls[0])["media"][0]["caption"]
    assert _u16(caption) <= 1024
    assert len(_visible(caption)) < _u16(caption)  # emoji are 2 UTF-16 units each


async def test_watch_keyword_capped_in_caption(session):
    _alert(session, 1)
    alert = session.query(Alert).one()
    alert.watch_keyword = "k" * 100
    session.flush()
    with respx.mock(assert_all_called=False) as mock:
        album, photo, msg = _routes(mock)
        await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    sent = [c for r in (album, photo, msg) for c in r.calls][0]
    body = _body(sent)
    text = body.get("caption") or body["text"]
    assert "k" * 40 in text and "k" * 41 not in text


async def test_token_never_logged_by_httpx(session, caplog):
    _alert(session, 1)
    _alert(session, 2)
    caplog.set_level(logging.DEBUG)
    # real httpx client (respx patches the transport), so httpx's own request logging runs
    with respx.mock(assert_all_called=False) as mock:
        album, _, _ = _routes(mock)
        n = await send_pending(session, _settings(), now=NOW, local_now=LOCAL)
    assert n == 2 and album.call_count == 1
    assert TOKEN not in caplog.text


async def test_app_url_is_escaped(session):
    for i in range(2):
        _alert(session, i, image=False)
    with respx.mock(assert_all_called=False) as mock:
        _, _, msg = _routes(mock)
        await send_pending(session, _settings(app_url="http://h/?a=1&b=<2>"), AlertsConfig(telegram_max_items=1),
                           now=NOW, local_now=LOCAL)
    text = _body(msg.calls[0])["text"]
    assert "a=1&amp;b=&lt;2&gt;/alerts" in text
