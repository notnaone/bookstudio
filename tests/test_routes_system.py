from __future__ import annotations


async def test_heartbeat_returns_status(client):
    r = await client.get("/api/heartbeat")
    assert r.status_code == 200
    body = r.json()
    assert "active_sessions" in body
    assert body["active_sessions"] == 0
