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
        "connectors": [{"name": "etsy", "kind": "product", "configured": True, "enabled": True}],
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
    assert "test-key" not in client.get("/api/settings").text
