import json
from datetime import date, datetime
from pathlib import Path

import httpx
import respx
from sqlalchemy import select

from app.config import Settings
from app.connectors.espn_events import EventsConfig, League, Stage
from app.models import Alert
from app.services import events_watch
from app.settings_store import set_setting

FIXTURE = json.loads((Path(__file__).parent / "fixtures/espn/mlb_postseason.json").read_text())
MLB = League("baseball", "mlb", "MLB", [Stage("World Series", True, "World Series", "{team} vô địch World Series {year}")])
NOW = datetime(2026, 10, 30, 4, 0)


async def _no_sleep(_):
    return None


@respx.mock
async def test_new_finals_become_alerts_once_and_are_sent(session_factory, monkeypatch):
    route = respx.get(MLB.url).mock(side_effect=lambda r: httpx.Response(
        200, json=FIXTURE if "dates" not in r.url.params else {"season": {"type": 3, "year": 2026}, "events": []}))
    sent = []

    async def fake_send(session, settings, kinds=None):
        sent.append(kinds)
        for a in session.scalars(select(Alert).where(Alert.sent_at.is_(None), Alert.kind.in_(kinds))):
            a.sent_at = NOW

    monkeypatch.setattr(events_watch, "send_pending", fake_send)
    cfg = EventsConfig([MLB])
    new = await events_watch.run_events(session_factory, Settings(_env_file=None), config=cfg, now=NOW,
                                        us_today=date(2026, 10, 29), sleep=_no_sleep)
    assert [(a["level"], a["title"]) for a in new] == [
        (1, "World Series 2026 · Game 4"), (2, "Cleveland Guardians vô địch World Series 2026")]
    assert new[0]["reason"] == "MLB · CLE 9–5 CHW · CLE leads series 3-1"
    assert new[1]["reason"] == "MLB · Game 6: CLE 9–5 CHW · CLE wins series 4-2"
    assert all(a["sent"] for a in new) and sent == [("event",)]
    assert route.calls[1].request.url.params["dates"] == "20261028"

    again = await events_watch.run_events(session_factory, Settings(_env_file=None), config=cfg, now=NOW,
                                          us_today=date(2026, 10, 29), sleep=_no_sleep)
    assert again == []
    with session_factory() as s:
        assert len(s.scalars(select(Alert)).all()) == 2


@respx.mock
async def test_espn_failure_and_disabled(session_factory, monkeypatch):
    respx.get(MLB.url).mock(return_value=httpx.Response(404))

    async def no_send(*a, **k):
        return 0

    monkeypatch.setattr(events_watch, "send_pending", no_send)
    cfg = EventsConfig([MLB])
    assert await events_watch.run_events(session_factory, Settings(_env_file=None), config=cfg, now=NOW,
                                         sleep=_no_sleep) == []
    with session_factory() as s:
        set_setting(s, "connectors_enabled", {"events": False})
        s.commit()
    assert await events_watch.run_events(session_factory, Settings(_env_file=None), config=cfg) is None


def test_send_pending_kinds_filter_and_quiet_hours(session):
    """Only event alerts go out; quiet hours still hold them."""
    import asyncio

    from app.analysis.alerts import AlertsConfig
    from app.notify.telegram import send_pending

    for kind in ("event", "niche"):
        session.add(Alert(kind=kind, subject_id=1, level=1, priority=1, title=kind, reason="r", link="/",
                          scan_date=date(2026, 10, 30), created_at=NOW))
    session.flush()
    settings = Settings(telegram_bot_token="t", telegram_chat_id="c", _env_file=None)
    cfg = AlertsConfig(quiet_start=22, quiet_end=7)
    with respx.mock:
        route = respx.post(url__regex=r"https://api\.telegram\.org/.*").mock(
            return_value=httpx.Response(200, json={"ok": True}))
        quiet = asyncio.run(send_pending(session, settings, cfg, now=NOW,
                                         local_now=datetime(2026, 10, 30, 23), kinds=("event",)))
        assert quiet == 0 and route.call_count == 0
        n = asyncio.run(send_pending(session, settings, cfg, now=NOW,
                                     local_now=datetime(2026, 10, 30, 9), kinds=("event",)))
    assert n == 1
    assert {a.kind: a.sent_at is not None for a in session.scalars(select(Alert))} == {"event": True, "niche": False}
