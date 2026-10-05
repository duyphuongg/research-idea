def test_ping(client):
    resp = client.get("/api/ping")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_cors_allows_frontend_origin(client):
    resp = client.get("/api/ping", headers={"Origin": "http://localhost:3000"})
    assert resp.headers["access-control-allow-origin"] == "http://localhost:3000"
