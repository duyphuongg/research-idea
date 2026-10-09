from datetime import date, datetime, timedelta

import pytest

from app.keywords import get_or_create_keyword
from app.models import KeywordRelation, KeywordScore, Seed, TrendSignal

TODAY = date(2026, 10, 5)


@pytest.fixture
def data(session):
    nurse = get_or_create_keyword(session, "nurse")
    nurse.first_seen_at = datetime(2026, 8, 1)
    gift = get_or_create_keyword(session, "nurse gift", origin="discovered", has_parent=True)
    gift.first_seen_at = datetime(2026, 10, 3)
    news = get_or_create_keyword(session, "braves dodgers game", origin="discovered")
    session.add(Seed(keyword="nurse"))
    session.add(
        KeywordRelation(parent_id=nurse.id, child_id=gift.id, source="etsy_tags", last_seen=TODAY)
    )
    scored = (
        (nurse, 80.0, ["etsy"]),
        (gift, 60.0, ["etsy_tags"]),
        (news, 90.0, ["google_daily"]),
    )
    for kw, score, sources in scored:
        session.add(
            KeywordScore(
                keyword_id=kw.id, date=TODAY, score=score, demand=0.5, momentum=None,
                competition=None, growth=None, sources_rising=0, sources=sources,
            )
        )
    session.add(
        KeywordScore(
            keyword_id=nurse.id, date=TODAY - timedelta(days=1), score=70.0,
            sources_rising=0, sources=["etsy"],
        )
    )
    session.add(
        KeywordScore(
            keyword_id=nurse.id, date=TODAY - timedelta(days=40), score=1.0,
            sources_rising=0, sources=["etsy"],
        )
    )
    session.add_all([
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day",
                    value=5.0, date=TODAY - timedelta(days=1)),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day",
                    value=7.0, date=TODAY),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="listing_count_tshirt",
                    value=1000.0, date=TODAY),
        TrendSignal(keyword_id=nurse.id, source="etsy", metric="views_per_day",
                    value=1.0, date=TODAY - timedelta(days=45)),
        TrendSignal(keyword_id=nurse.id, source="amazon", metric="title_phrase_count",
                    value=3.0, date=TODAY),  # retired source: never charted
    ])
    session.commit()
    return {"nurse": nurse.id, "gift": gift.id, "news": news.id}


def test_empty_when_no_scores(client):
    assert client.get("/api/trends").json() == {"date": None, "items": []}


def test_lists_latest_scores_pod_only_by_default(client, data):
    body = client.get("/api/trends").json()
    assert body["date"] == "2026-10-05"
    assert [i["keyword"] for i in body["items"]] == ["nurse", "nurse gift"]
    nurse, gift = body["items"]
    assert nurse["is_seed"] is True and nurse["is_new"] is False
    assert nurse["sparkline"] == [70.0, 80.0]
    assert gift["is_seed"] is False and gift["is_new"] is True
    assert gift["origin"] == "discovered"


def test_filters(client, data):
    all_items = client.get("/api/trends?pod_only=false").json()["items"]
    assert [i["keyword"] for i in all_items] == ["brave dodger game", "nurse", "nurse gift"]
    by_source = client.get("/api/trends?source=etsy_tags").json()["items"]
    assert [i["keyword"] for i in by_source] == ["nurse gift"]
    by_origin = client.get("/api/trends?origin=seed").json()["items"]
    assert [i["keyword"] for i in by_origin] == ["nurse"]
    assert len(client.get("/api/trends?limit=1").json()["items"]) == 1


def test_detail(client, data):
    body = client.get(f"/api/trends/{data['nurse']}").json()
    assert (body["keyword"], body["is_seed"], body["trend"]["score"]) == ("nurse", True, 80.0)
    series = {(s["source"], s["metric"]): s["points"] for s in body["signals"]}
    # 45-day-old point excluded
    assert [p["value"] for p in series[("etsy", "views_per_day")]] == [5.0, 7.0]
    assert ("etsy", "listing_count_tshirt") in series
    assert not any(src == "amazon" for src, _ in series)
    assert body["related"] == [{
        "keyword_id": data["gift"], "keyword": "nurse gift", "relation": "child",
        "source": "etsy_tags", "score": 60.0, "is_pod_relevant": True,
    }]
    child = client.get(f"/api/trends/{data['gift']}").json()
    assert child["related"][0]["relation"] == "parent"
    assert child["related"][0]["keyword"] == "nurse"


def test_detail_404(client):
    assert client.get("/api/trends/999").status_code == 404
