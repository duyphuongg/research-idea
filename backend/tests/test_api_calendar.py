from datetime import date

from app.analysis.us_calendar import Occurrence, load_calendar
from app.keywords import get_or_create_keyword
from app.models import KeywordScore, Seed
from app.services.calendar_ideas import seed_ideas

TODAY = "2026-10-05"


def score(session, kw, value, day=date(2026, 10, 5)):
    session.add(
        KeywordScore(keyword_id=kw.id, date=day, score=value, sources_rising=0, sources=["etsy"])
    )


def test_calendar_lists_upcoming_events_with_phases(client):
    body = client.get(f"/api/calendar?today={TODAY}").json()
    assert body["today"] == TODAY and body["fulfillment_days"] == 10
    keys = [e["key"] for e in body["events"]]
    assert keys[:4] == [
        "hispanic_heritage_month",
        "breast_cancer_awareness",
        "halloween",
        "dia_de_los_muertos",
    ]
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
    assert keys == [
        "hispanic_heritage_month",
        "breast_cancer_awareness",
        "halloween",
        "dia_de_los_muertos",
    ]
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


def test_seed_idea_templates_and_cross_seeds(client, session):
    session.add_all(
        [Seed(keyword="nurse"), Seed(keyword="dog mom"), Seed(keyword="old", active=False)]
    )
    session.commit()
    events = {e["key"]: e for e in client.get(f"/api/calendar?today={TODAY}").json()["events"]}
    defs, _ = load_calendar()
    for key in ("nurses_week", "teacher_appreciation_week"):
        defn = next(d for d in defs if d.key == key)
        occ = Occurrence(event=defn, start=date(2026, 5, 4), end=date(2026, 5, 8))
        assert seed_ideas(session, occ, {}) == []
    assert [i["keyword"] for i in events["black_friday"]["seed_ideas"]] == [
        "nurse christmas gift",
        "dog mom christmas gift",
    ]
    assert [i["keyword"] for i in events["sale_11_11"]["seed_ideas"]] == [
        "nurse gift",
        "dog mom gift",
    ]
    assert [i["keyword"] for i in events["halloween"]["seed_ideas"]] == [
        "halloween nurse",
        "halloween dog mom",
    ]


def test_is_seed_only_for_active_seed_text(client, session):
    session.add_all(
        [
            Seed(keyword="ghost"),
            Seed(keyword="Halloween  Ghost", active=False),
            Seed(keyword="nurse"),
            Seed(keyword="Halloween Nurse"),
        ]
    )
    session.commit()
    events = {e["key"]: e for e in client.get(f"/api/calendar?today={TODAY}").json()["events"]}
    ideas = {i["keyword"]: i["is_seed"] for i in events["halloween"]["seed_ideas"]}
    assert ideas["halloween ghost"] is False  # matching seed is inactive
    assert ideas["halloween nurse"] is True  # case-insensitive match of active seed


def test_seed_whose_tokens_are_within_lead_is_skipped(client, session):
    session.add_all([Seed(keyword="halloween"), Seed(keyword="witch")])
    session.commit()
    events = {e["key"]: e for e in client.get(f"/api/calendar?today={TODAY}").json()["events"]}
    assert [i["keyword"] for i in events["halloween"]["seed_ideas"]] == ["halloween witch"]
