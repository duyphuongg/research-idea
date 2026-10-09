import html as _html
import json
import re
from datetime import date, datetime, timedelta

import httpx
import respx

from app.analysis.alerts import AlertsConfig
from app.config import Settings
from app.keywords import get_or_create_keyword
from app.models import Alert, KeywordScore, ListingSignal, Product, Seed
from app.pipeline.scan import run_scan
from app.services.digest import build_digest, maybe_send_weekly_digest
from app.settings_store import get_setting, set_setting

TODAY = date(2026, 10, 7)  # Wednesday; Halloween is 24 days away
NOW = datetime(2026, 10, 7, 1, 0)  # UTC
L = date(2026, 10, 6)  # latest score date
TOKEN = "123:secret"
BASE = f"https://api.telegram.org/bot{TOKEN}"
OK = httpx.Response(200, json={"ok": True})
MONDAY_8 = datetime(2026, 10, 5, 8, 0)
APP = "http://mac.ts.net:3737"


def _settings(**kw):
    kw.setdefault("app_url", APP)
    return Settings(_env_file=None, telegram_bot_token=TOKEN, telegram_chat_id="42", **kw)


def _visible(text: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", text))


def _score(session, text, history, *, relevant=True):
    kw = get_or_create_keyword(session, text)
    kw.is_pod_relevant = relevant
    for d, s in history:
        session.add(KeywordScore(keyword_id=kw.id, score=s, date=d))
    session.flush()
    return kw


def _alert(session, i, kind="listing", created=NOW, watch=None, level=1):
    session.add(Alert(kind=kind, subject_id=i, level=level, title=f"T{i}", reason="r", link=f"/x/{i}",
                      watch_keyword=watch, scan_date=created.date(), created_at=created))
    session.flush()


def _listing(session, i, title, status, query="graphic tee", updated=L):
    p = Product(source="etsy", external_id=f"p{i}", title=title, url="u", product_type="tshirt")
    session.add(p)
    session.flush()
    session.add(ListingSignal(product_id=p.id, discovered_on=L, discovery_query=query, status=status,
                              updated_on=updated))
    session.flush()


def test_header_always_present(session):
    text = build_digest(session, TODAY, None, now=NOW)
    assert text.startswith("📊 <b>Tổng kết 7 ngày qua (30/09 – 06/10)</b>")


def test_rising_section_with_history(session):
    week_ago = L - timedelta(days=7)
    a = _score(session, "aaa tee", [(week_ago, 50), (L, 64)])
    _score(session, "bbb tee", [(week_ago, 60), (L, 62)])
    _score(session, "ccc tee", [(week_ago, 70), (L, 65)])
    _score(session, "ddd tee", [(week_ago, 10), (L, 90)], relevant=False)
    text = build_digest(session, TODAY, APP, now=NOW)
    assert "🚀 <b>Ngách tăng mạnh nhất 7 ngày</b>" in text
    vis = _visible(text)
    assert "1. aaa tee — 64 (+14)" in vis and "2. bbb tee — 62 (+2)" in vis
    assert "ccc tee" not in vis and "ddd tee" not in vis
    assert f'<a href="{APP}/trends/{a.id}">aaa tee</a>' in text


def test_rising_fallback_without_history(session):
    _score(session, "aaa tee", [(L, 64)])
    _score(session, "bbb tee", [(L, 72)])
    text = build_digest(session, TODAY, None, now=NOW)
    assert "🚀 <b>Ngách điểm cao nhất</b>" in text
    vis = _visible(text)
    assert vis.index("1. bbb tee — 72") < vis.index("2. aaa tee — 64")
    assert "(+" not in vis
    assert "<a " not in text.split("Ngách điểm cao nhất")[1].split("\n\n")[0]


def test_watchlist_line(session):
    session.add(Seed(keyword="football mom"))
    _score(session, "football mom", [(L - timedelta(days=3), 40), (L, 58)])
    _listing(session, 1, "Football Mom Game Day Tee", "super_breakout")
    _listing(session, 2, "Funny tee", "steady_grower", query="football mom shirt")
    _listing(session, 3, "Footballmomentum tee", "super_breakout")  # not a whole word
    _listing(session, 4, "Football mom tee", "calibrating")
    _listing(session, 5, "Football mom old", "super_breakout", updated=L - timedelta(days=1))
    _alert(session, 1, watch="football mom", created=NOW - timedelta(days=1))
    _alert(session, 2, watch="football mom", created=NOW - timedelta(days=6))
    _alert(session, 3, watch="football mom", created=NOW - timedelta(days=8))
    _alert(session, 4, watch="other")
    session.add(Seed(keyword="ghost"))
    session.flush()
    text = build_digest(session, TODAY, None, now=NOW)
    assert "👀 <b>Watchlist</b>" in text
    vis = _visible(text)
    assert "• football mom: 58 điểm · 2 bứt phá · 2 tin" in vis
    assert "• ghost: — điểm · 0 bứt phá · 0 tin" in vis


def test_watchlist_omitted_without_seeds(session):
    assert "Watchlist" not in build_digest(session, TODAY, None, now=NOW)


def test_upcoming_calendar(session):
    vis = _visible(build_digest(session, TODAY, None, now=NOW))
    assert "📅 Sắp tới" in vis
    assert "• Halloween 31/10 — còn 24 ngày" in vis
    section = vis.split("📅 Sắp tới")[1].split("\n\n")[0]
    assert section.count("•") == 4
    assert "Breast Cancer" not in section  # started before today


def test_upcoming_today(session):
    vis = _visible(build_digest(session, date(2026, 10, 31), None, now=NOW))
    assert "• Halloween 31/10 — hôm nay" in vis


def test_alert_summary(session):
    for i in range(2):
        _alert(session, i, kind="niche")
    for i in range(3):
        _alert(session, 10 + i, kind="listing")
    _alert(session, 20, kind="hot_product", created=NOW - timedelta(days=2))
    _alert(session, 21, kind="hot_product", created=NOW - timedelta(days=9))
    text = build_digest(session, TODAY, APP, now=NOW)
    assert "🔔 <b>Tuần qua:</b> 6 tin (2 🚀 · 3 🔥 · 1 ⭐)" in text
    assert "🛒" not in text
    assert text.endswith(f'<a href="{APP}/alerts">Mở app →</a>')


def test_alert_summary_empty_without_link(session):
    text = build_digest(session, TODAY, None, now=NOW)
    assert "🔔 <b>Tuần qua:</b> chưa có tin" in text
    assert "Mở app" not in text


def test_escaping(session):
    _score(session, "x <b> tee", [(L, 64)])
    session.add(Seed(keyword="a&b <i>"))
    session.flush()
    text = build_digest(session, TODAY, APP, now=NOW)
    assert "x &lt;b&gt; tee" in text and "a&amp;b &lt;i&gt;" in text
    assert "<b> tee" not in text


def test_many_seeds_stay_under_limit(session):
    for i in range(300):
        session.add(Seed(keyword=f"very long watch keyword number {i} " + "x" * 40))
    session.flush()
    text = build_digest(session, TODAY, APP, now=NOW)
    assert len(text) <= 4096
    assert text.startswith("📊") and "Tuần qua" in text


async def test_weekly_digest_once_per_week(session):
    cfg = AlertsConfig()
    set_setting(session, "digest_last_week", "2026-W40")  # not the first run
    with respx.mock() as mock:
        route = mock.post(f"{BASE}/sendMessage").mock(return_value=OK)
        assert await maybe_send_weekly_digest(session, _settings(), local_now=MONDAY_8, cfg=cfg)
        assert not await maybe_send_weekly_digest(session, _settings(), local_now=MONDAY_8 + timedelta(hours=12),
                                                  cfg=cfg)
        assert route.call_count == 1
        body = json.loads(route.calls[0].request.content.decode())
        assert body["text"].startswith("📊 <b>Tổng kết 7 ngày qua (28/09 – 04/10)</b>")
        assert body["parse_mode"] == "HTML" and not body.get("disable_notification")
        assert get_setting(session, "digest_last_week") == "2026-W41"
        assert await maybe_send_weekly_digest(session, _settings(), local_now=MONDAY_8 + timedelta(days=7),
                                              cfg=cfg)
        assert route.call_count == 2
    assert get_setting(session, "digest_last_week") == "2026-W42"


async def test_weekly_digest_first_run_only_stores_week(session):
    with respx.mock(assert_all_called=False) as mock:
        assert not await maybe_send_weekly_digest(session, _settings(), local_now=MONDAY_8 + timedelta(days=2),
                                                  cfg=AlertsConfig())
    assert not mock.calls
    assert get_setting(session, "digest_last_week") == "2026-W41"


async def test_weekly_digest_not_in_quiet_hours(session):
    with respx.mock(assert_all_called=False) as mock:
        assert not await maybe_send_weekly_digest(session, _settings(), local_now=datetime(2026, 10, 5, 0, 30),
                                                  cfg=AlertsConfig())
    assert not mock.calls and get_setting(session, "digest_last_week") is None


async def test_weekly_digest_not_configured(session):
    with respx.mock(assert_all_called=False) as mock:
        assert not await maybe_send_weekly_digest(session, Settings(_env_file=None), local_now=MONDAY_8,
                                                  cfg=AlertsConfig())
    assert not mock.calls


async def test_weekly_digest_failure_not_stored(session):
    set_setting(session, "digest_last_week", "2026-W40")
    with respx.mock() as mock:
        mock.post(f"{BASE}/sendMessage").mock(return_value=httpx.Response(500))
        assert not await maybe_send_weekly_digest(session, _settings(), local_now=MONDAY_8, cfg=AlertsConfig())
    assert get_setting(session, "digest_last_week") == "2026-W40"


async def test_run_scan_without_telegram_sends_nothing(session_factory):
    with respx.mock(assert_all_called=False) as mock:
        await run_scan(session_factory, [], today=TODAY)
    assert not mock.calls
    with session_factory() as s:
        assert get_setting(s, "digest_last_week") is None


def _shop(session, sid, name, sold_7d_ago, sold_now, title, *, days=7):
    from app.models import Shop, ShopSnapshot

    session.add(Shop(id=sid, name=name, first_seen=L - timedelta(days=days), last_seen=L))
    session.add(ShopSnapshot(shop_id=sid, date=L - timedelta(days=days), sold_count=sold_7d_ago))
    session.add(ShopSnapshot(shop_id=sid, date=L, sold_count=sold_now))
    session.add(Product(source="etsy", external_id=f"s{sid}", title=title, url="u", product_type="tshirt",
                        shop_id=sid))
    session.flush()


def test_top_shops_section(session):
    session.add(Seed(keyword="football mom"))
    session.add(Seed(keyword="ghost"))
    _shop(session, 1, "Alpha", 100, 140, "Football Mom Tee")         # +40
    _shop(session, 2, "Beta & Co", 10, 90, "Spooky Ghost Shirt")     # +80
    _shop(session, 3, "Gamma", 0, 20, "Football Mom Hoodie")         # +20
    _shop(session, 4, "Delta", 0, 10, "Ghost Tee")                   # +10, 4th
    _shop(session, 5, "Short", 0, 999, "Ghost Tee", days=3)          # under 7 days of history
    _shop(session, 6, "Other", 0, 500, "Cat Tee")                    # no watch keyword
    text = build_digest(session, TODAY, APP, now=NOW)
    section = text.split("🏪 <b>Shop ra đơn nhiều nhất 7 ngày</b>\n")[1].split("\n\n")[0]
    assert section.split("\n") == [
        f'• <a href="{APP}/shops/2">Beta &amp; Co</a> — +80 đơn',
        f'• <a href="{APP}/shops/1">Alpha</a> — +40 đơn',
        f'• <a href="{APP}/shops/3">Gamma</a> — +20 đơn',
    ]
    # right after the Watchlist section, before the calendar
    assert text.index("👀 <b>Watchlist</b>") < text.index("🏪") < text.index("📅")


def test_top_shops_without_app_url_is_plain(session):
    session.add(Seed(keyword="ghost"))
    _shop(session, 1, "Alpha", 0, 12, "Ghost Tee")
    text = build_digest(session, TODAY, None, now=NOW)
    assert "• Alpha — +12 đơn" in text


def test_top_shops_omitted_without_rows(session):
    session.add(Seed(keyword="ghost"))
    _shop(session, 1, "Alpha", 0, 12, "Cat Tee")
    assert "🏪" not in build_digest(session, TODAY, APP, now=NOW)


def test_alert_summary_counts_shop_alerts(session):
    _alert(session, 1, kind="listing")
    _alert(session, 2, kind="shop")
    _alert(session, 3, kind="hot_product")
    assert "🔔 <b>Tuần qua:</b> 3 tin (1 🔥 · 1 🏪 · 1 ⭐)" in build_digest(session, TODAY, None, now=NOW)


def test_top_shops_skips_zero_sales(session):
    session.add(Seed(keyword="ghost"))
    _shop(session, 1, "Flat", 50, 50, "Ghost Tee")      # +0
    _shop(session, 2, "Alpha", 0, 12, "Ghost Tee")
    text = build_digest(session, TODAY, APP, now=NOW)
    assert "Flat" not in text and "Alpha" in text


def test_top_shops_need_a_7_to_9_day_span(session):
    session.add(Seed(keyword="ghost"))
    _shop(session, 1, "Nine", 0, 30, "Ghost Tee", days=9)
    _shop(session, 2, "Gappy", 0, 999, "Ghost Tee", days=12)    # 12-day gap: not a 7-day value
    text = build_digest(session, TODAY, APP, now=NOW)
    assert "Nine" in text and "Gappy" not in text
