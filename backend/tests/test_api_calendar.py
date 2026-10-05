from datetime import date

from app.keywords import get_or_create_keyword
from app.models import KeywordScore, Seed

TODAY = "2026-10-05"


def score(session, kw, value, day=date(2026, 10, 5)):
    session.add(
        KeywordScore(keyword_id=kw.id, date=day, score=value, sources_rising=0, sources=["etsy"])
    )


def test_calendar_lists_upcoming_events_with_phases(client):
    body = client.get(f"/api/calendar?today={TODAY}").json()
    assert body["today"] == TODAY and body["fulfillment_days"] == 10
    keys = [e["key"] for e in body["events"]]
    assert keys[:3] == ["breast_cancer_awareness", "halloween", "sale_11_11"]
    halloween = next(e for e in body["events"] if e["key"] == "halloween")
    assert (halloween["days_until"], halloween["phase"], halloween["ship_by"]) == (
        26,
        "push",
        "2026-10-21",
    )
    assert halloween["phase_label"] == "📈 Đẩy mạnh"
    assert halloween["advice"]
    bf = next(e for e in body["events"] if e["key"] == "black_friday")
    assert (bf["type"], bf["ship_by"], bf["phase"]) == ("sale", None, "design")


def test_days_param_limits_horizon(client):
    keys = [e["key"] for e in client.get(f"/api/calendar?today={TODAY}&days=30").json()["events"]]
    assert keys == ["breast_cancer_awareness", "halloween"]
    assert client.get("/api/calendar?days=0").status_code == 422


def test_seed_ideas_and_radar_matches(client, session):
    session.add_all([Seed(keyword="nurse"), Seed(keyword="dog mom")])
    nurse_halloween = get_or_create_keyword(
        session, "halloween nurse", origin="discovered", has_parent=True
    )
    spooky = get_or_create_keyword(
        session, "spooky dog mom", origin="discovered", has_parent=True
    )
    other = get_or_create_keyword(session, "nurse gift", origin="discovered", has_parent=True)
    score(session, nurse_halloween, 50.9)
    score(session, spooky, 61.0)
    score(session, other, 70.0)
    session.commit()

    events = client.get(f"/api/calendar?today={TODAY}").json()["events"]
    halloween = next(e for e in events if e["key"] == "halloween")
    ideas = {i["keyword"]: i for i in halloween["seed_ideas"]}
    assert set(ideas) == {"halloween nurse", "halloween dog mom"}
    assert ideas["halloween nurse"]["score"] == 50.9
    assert ideas["halloween nurse"]["keyword_id"] == nurse_halloween.id
    assert ideas["halloween dog mom"]["keyword_id"] is None
    assert ideas["halloween dog mom"]["is_seed"] is False
    assert [m["keyword"] for m in halloween["radar_matches"]] == [
        "spooky dog mom",
        "halloween nurse",
    ]
