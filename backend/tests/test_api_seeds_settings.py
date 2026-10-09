def test_seed_crud(client):
    resp = client.post("/api/seeds", json={"keyword": "  Dog   Mom "})
    assert resp.status_code == 201
    seed = resp.json()
    assert seed["keyword"] == "dog mom"
    assert seed["active"] is True
    assert isinstance(seed["keyword_id"], int)

    assert client.post("/api/seeds", json={"keyword": "dog mom"}).status_code == 409
    assert client.post("/api/seeds", json={"keyword": "   "}).status_code == 422

    assert [s["keyword"] for s in client.get("/api/seeds").json()] == ["dog mom"]
    assert client.delete(f"/api/seeds/{seed['id']}").status_code == 204
    assert client.delete(f"/api/seeds/{seed['id']}").status_code == 404
    assert client.get("/api/seeds").json() == []


def test_settings_defaults(client):
    body = client.get("/api/settings").json()
    assert body == {
        "scan_hour_utc": 11,
        "connectors": [
            {"name": "etsy", "kind": "product", "configured": True, "enabled": True},
            {"name": "google_suggest", "kind": "trend", "configured": True, "enabled": True},
            {"name": "google_daily", "kind": "trend", "configured": True, "enabled": True},
            {"name": "etsy_signals", "kind": "signals", "configured": True, "enabled": True},
            {"name": "etsy_counts", "kind": "counts", "configured": True, "enabled": True},
            {"name": "nfl", "kind": "sports", "configured": True, "enabled": True},
        ],
    }


def test_settings_update_merges_and_validates(client):
    body = client.put("/api/settings", json={"connectors_enabled": {"etsy": False}}).json()
    assert body["connectors"][0]["enabled"] is False

    body = client.put("/api/settings", json={"scan_hour_utc": 3}).json()
    assert body["scan_hour_utc"] == 3
    assert body["connectors"][0]["enabled"] is False  # untouched

    assert client.put("/api/settings", json={"scan_hour_utc": 24}).status_code == 422
    assert client.put("/api/settings", json={"connectors_enabled": {"nope": True}}).status_code == 400


def test_settings_never_exposes_api_key(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["connectors"][0]["configured"] is True
    assert "test-key" not in resp.text

    resp = client.get("/api/health/sources")
    assert resp.status_code == 200
    assert resp.json()[0]["configured"] is True
    assert "test-key" not in resp.text


def test_settings_update_reschedules_only_when_hour_given(client):
    calls = []

    class FakeScheduler:
        def reschedule_job(self, job_id, trigger=None):
            calls.append((job_id, trigger))

    client.app.state.scheduler = FakeScheduler()

    client.put("/api/settings", json={"connectors_enabled": {"etsy": False}})
    assert calls == []

    client.put("/api/settings", json={"scan_hour_utc": 4})
    assert len(calls) == 1
    assert calls[0][0] == "daily_scan"


def test_following_discovered_keyword_marks_it_relevant(client, session):
    from app.keywords import get_or_create_keyword
    from app.models import Keyword

    kw = get_or_create_keyword(session, "braves dodgers game", origin="discovered")
    session.commit()
    assert kw.is_pod_relevant is False

    resp = client.post("/api/seeds", json={"keyword": "braves dodgers game"})
    assert resp.status_code == 201
    session.expire_all()
    assert session.get(Keyword, kw.id).is_pod_relevant is True


def test_settings_can_disable_etsy_signals(client):
    resp = client.put("/api/settings", json={"connectors_enabled": {"etsy_signals": False}})
    assert resp.status_code == 200
    entry = next(c for c in resp.json()["connectors"] if c["name"] == "etsy_signals")
    assert entry["enabled"] is False
