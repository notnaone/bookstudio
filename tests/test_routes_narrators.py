from __future__ import annotations


async def test_list_narrators_empty(client):
    r = await client.get("/api/narrators")
    assert r.status_code == 200
    assert r.json() == {"narrators": []}


async def test_create_narrator_minimal(client):
    r = await client.post("/api/narrators", json={"name": "Chris"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Chris"
    assert body["calendar_alias"] is None
    assert body["notes"] is None


async def test_create_narrator_full(client):
    r = await client.post(
        "/api/narrators",
        json={"name": "Christina", "calendar_alias": "Christina", "notes": "fast"},
    )
    body = r.json()
    assert body["name"] == "Christina"
    assert body["calendar_alias"] == "Christina"
    assert body["notes"] == "fast"


async def test_create_narrator_rejects_blank_name(client):
    r = await client.post("/api/narrators", json={"name": ""})
    assert r.status_code == 400


async def test_create_narrator_rejects_duplicate_alias(client):
    await client.post("/api/narrators", json={"name": "A", "calendar_alias": "shared"})
    r = await client.post(
        "/api/narrators", json={"name": "B", "calendar_alias": "shared"}
    )
    assert r.status_code == 400
    assert "calendar_alias" in r.json()["detail"].lower()


async def test_get_narrator_by_id(client):
    r = await client.post("/api/narrators", json={"name": "Detail"})
    nid = r.json()["id"]
    r2 = await client.get(f"/api/narrators/{nid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Detail"


async def test_get_narrator_404(client):
    r = await client.get("/api/narrators/9999")
    assert r.status_code == 404


async def test_patch_narrator_updates(client):
    r = await client.post("/api/narrators", json={"name": "Old"})
    nid = r.json()["id"]
    r2 = await client.patch(
        f"/api/narrators/{nid}",
        json={"name": "New", "calendar_alias": "NewAlias", "notes": "n"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["name"] == "New"
    assert body["calendar_alias"] == "NewAlias"


async def test_patch_narrator_clears_alias_with_null(client):
    r = await client.post(
        "/api/narrators", json={"name": "X", "calendar_alias": "tobe_cleared"}
    )
    nid = r.json()["id"]
    r2 = await client.patch(
        f"/api/narrators/{nid}", json={"calendar_alias": None}
    )
    assert r2.status_code == 200
    assert r2.json()["calendar_alias"] is None
