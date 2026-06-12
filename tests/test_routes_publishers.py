from __future__ import annotations


async def test_list_publishers_empty(client):
    r = await client.get("/api/publishers")
    assert r.status_code == 200
    assert r.json() == {"publishers": []}


async def test_create_publisher(client):
    r = await client.post(
        "/api/publishers", json={"name": "Penguin", "notes": "fiction imprint"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Penguin"
    assert body["notes"] == "fiction imprint"
    assert "id" in body


async def test_create_publisher_rejects_blank_name(client):
    r = await client.post("/api/publishers", json={"name": "  "})
    assert r.status_code == 400


async def test_create_publisher_rejects_missing_name(client):
    r = await client.post("/api/publishers", json={"notes": "no name"})
    assert r.status_code == 400


async def test_patch_publisher_updates_fields(client):
    r = await client.post("/api/publishers", json={"name": "Original"})
    pid = r.json()["id"]
    r2 = await client.patch(
        f"/api/publishers/{pid}",
        json={"name": "Renamed", "notes": "added note"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "Renamed"
    assert r2.json()["notes"] == "added note"


async def test_patch_publisher_404(client):
    r = await client.patch("/api/publishers/9999", json={"name": "x"})
    assert r.status_code == 404


async def test_list_publishers_after_create(client):
    await client.post("/api/publishers", json={"name": "A"})
    await client.post("/api/publishers", json={"name": "B"})
    r = await client.get("/api/publishers")
    names = sorted(p["name"] for p in r.json()["publishers"])
    assert names == ["A", "B"]
