from __future__ import annotations


async def test_heartbeat_returns_status(client):
    r = await client.get("/api/heartbeat")
    assert r.status_code == 200
    body = r.json()
    assert "active_sessions" in body
    assert body["active_sessions"] == 0


async def test_root_redirects_to_library_when_configured(client):
    r = await client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/library"


async def test_setup_page_returns_html(client):
    r = await client.get("/setup")
    assert r.status_code == 200
    assert "<form" in r.text
