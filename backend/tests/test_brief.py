from datetime import date, datetime

import httpx
import respx

from app.analysis.alerts import AlertsConfig
from app.config import Settings
from app.keywords import get_or_create_keyword
from app.models import Alert, KeywordScore, NflMoment, NflPerformance, WorkItem
from app.services.brief import build_brief, maybe_send_morning_brief
from app.settings_store import get_setting

TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 1, 0)


def _data(session):
    for text, comp, demand in (("pickleball lover", 0.1, 0.9), ("nfl mom", 0.0, 1.0), ("game day", 0.9, 0.9),
                               ("listed niche", 0.0, 0.95)):
        kw = get_or_create_keyword(session, text, origin="discovered")
        kw.is_pod_relevant = True
        session.add(KeywordScore(keyword_id=kw.id, date=TODAY, score=60, demand=demand, momentum=0.8,
                                 competition=comp, sources_rising=0, sources=["etsy"]))
        if text == "listed niche":
            session.add(WorkItem(subject_kind="keyword", subject_id=kw.id, status="listed"))
        if text == "game day":
            session.add(WorkItem(subject_kind="keyword", subject_id=kw.id, status="designing",
                                 updated_at=datetime(2026, 10, 1)))
    session.add(NflMoment(query="jayden daniels injury", traffic=50000, first_seen=NOW, last_seen=NOW, news=[]))
    session.add(Alert(kind="niche", subject_id=1, level=1, priority=1, title="x", reason="r", link="/",
                      scan_date=TODAY, created_at=NOW))
    session.flush()


def test_build_brief_sections(session):
    _data(session)
    text = build_brief(session, TODAY, "http://app", now=NOW)
    assert text.startswith("☀️ <b>Hôm nay làm gì — 09/10</b>")
    assert "📅 <b>Mùa vụ</b>" in text and "Halloween" in text
    assert 'href="http://app/niche?keyword=pickleball+lover">pickleball lover</a> — cơ hội' in text
    assert "nfl mom" not in text  # trademark (red) is skipped
    assert "listed niche" not in text  # already listed
    assert "jayden daniels injury (50.000+ lượt tìm)" in text
    assert "1 mục đang thiết kế ≥ 5 ngày chưa cập nhật: game day" in text
    assert "1 tin chưa đọc" in text


def test_build_brief_without_data_has_only_the_calendar(session):
    text = build_brief(session, TODAY, None, now=NOW)
    assert "Mùa vụ" in text and "Ngách" not in text and "NFL" not in text and "tin chưa đọc" not in text


async def test_send_once_per_morning(session):
    _data(session)
    settings = Settings(telegram_bot_token="t", telegram_chat_id="c", _env_file=None)
    cfg = AlertsConfig()
    with respx.mock:
        route = respx.post(url__regex=r"https://api\.telegram\.org/.*").mock(
            return_value=httpx.Response(200, json={"ok": True}))
        async with httpx.AsyncClient() as client:
            evening = await maybe_send_morning_brief(session, settings, local_now=datetime(2026, 10, 9, 20),
                                                     cfg=cfg, client=client)
            first = await maybe_send_morning_brief(session, settings, local_now=datetime(2026, 10, 9, 8),
                                                   cfg=cfg, client=client)
            again = await maybe_send_morning_brief(session, settings, local_now=datetime(2026, 10, 9, 9),
                                                   cfg=cfg, client=client)
    assert (evening, first, again) == (False, True, False)
    assert route.call_count == 1 and get_setting(session, "brief_last_date") == "2026-10-09"
