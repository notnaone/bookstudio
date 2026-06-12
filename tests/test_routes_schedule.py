from __future__ import annotations

import pytest


def _manual_payload(**overrides) -> dict:
    base = {
        "source": "manual",
        "kind": "recording",
        "start_time": "2026-06-20T09:00:00+00:00",
        "end_time": "2026-06-20T11:00:00+00:00",
        "raw_title": "Manual recording block",
        "notes": "studio prep",
    }
    base.update(overrides)
    return base


async def _create_manual(client, **overrides) -> dict:
    r = await client.post("/api/schedule", json=_manual_payload(**overrides))
    assert r.status_code == 201, r.text
    return r.json()


async def _seed_mirror_row(conn, *, uid: str = "gcal-evt-1") -> int:
    cur = conn.execute(
        "INSERT INTO schedule_item"
        " (source, google_event_id, start_time, end_time, raw_title, action_status)"
        " VALUES ('studio_1', ?, '2026-06-21T10:00:00+00:00',"
        " '2026-06-21T12:00:00+00:00', 'Chris - Mirror Event', 'pending')",
        (uid,),
    )
    return cur.lastrowid


async def test_create_manual_schedule_item(client):
    item = await _create_manual(client)
    assert item["id"] > 0
    assert item["source"] == "manual"
    assert item["kind"] == "recording"
    assert item["raw_title"] == "Manual recording block"
    assert item["google_event_id"] is None
    assert item["action_status"] == "pending"
    assert item["resolved_book_title"] is None
    assert item["resolved_narrator_name"] is None


async def test_create_manual_rejects_google_event_id(client):
    payload = _manual_payload(google_event_id="should-not-send")
    r = await client.post("/api/schedule", json=payload)
    assert r.status_code == 400
    assert "google_event_id" in r.json()["detail"].lower()


async def test_create_manual_requires_kind(client):
    payload = _manual_payload()
    del payload["kind"]
    r = await client.post("/api/schedule", json=payload)
    assert r.status_code == 400


async def test_list_schedule_filters_by_source_and_date_range(client):
    await _create_manual(
        client,
        start_time="2026-06-10T09:00:00+00:00",
        end_time="2026-06-10T11:00:00+00:00",
        raw_title="Early manual",
    )
    await _create_manual(
        client,
        start_time="2026-06-25T09:00:00+00:00",
        end_time="2026-06-25T11:00:00+00:00",
        raw_title="Late manual",
    )

    r = await client.get(
        "/api/schedule",
        params={
            "from": "2026-06-20T00:00:00+00:00",
            "to": "2026-06-30T00:00:00+00:00",
            "source": "manual",
        },
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["raw_title"] == "Late manual"


async def test_patch_manual_row_and_resolved_fields(client, conn):
    narrator_id = conn.execute(
        "INSERT INTO narrator (name) VALUES ('Test Narrator')"
    ).lastrowid
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('test-book', 'Test Book', 'txt', '/x', '/x')"
    ).lastrowid

    item = await _create_manual(client)
    item_id = item["id"]

    r = await client.patch(
        f"/api/schedule/{item_id}",
        json={
            "action_status": "started",
            "notes": "updated note",
            "resolved_narrator_id": narrator_id,
            "resolved_book_id": book_id,
        },
    )
    assert r.status_code == 200, r.text
    patched = r.json()
    assert patched["action_status"] == "started"
    assert patched["notes"] == "updated note"
    assert patched["resolved_narrator_id"] == narrator_id
    assert patched["resolved_book_id"] == book_id
    assert patched["resolved_narrator_name"] == "Test Narrator"
    assert patched["resolved_book_title"] == "Test Book"
    assert patched["resolved_at"] is not None


async def test_patch_mirror_row_allows_action_status_only(client, conn):
    mirror_id = await _seed_mirror_row(conn)

    r = await client.patch(
        f"/api/schedule/{mirror_id}",
        json={"action_status": "started"},
    )
    assert r.status_code == 200
    assert r.json()["action_status"] == "started"


async def test_patch_mirror_row_rejects_calendar_fields(client, conn):
    mirror_id = await _seed_mirror_row(conn, uid="gcal-evt-2")

    r = await client.patch(
        f"/api/schedule/{mirror_id}",
        json={"raw_title": "Hijacked title"},
    )
    assert r.status_code == 400
    assert "calendar" in r.json()["detail"].lower() or "mirror" in r.json()["detail"].lower()


async def test_delete_manual_row(client):
    item = await _create_manual(client)
    r = await client.delete(f"/api/schedule/{item['id']}")
    assert r.status_code == 204

    r = await client.get("/api/schedule")
    assert r.status_code == 200
    assert all(i["id"] != item["id"] for i in r.json()["items"])


async def test_delete_mirror_row_forbidden(client, conn):
    mirror_id = await _seed_mirror_row(conn, uid="gcal-evt-3")
    r = await client.delete(f"/api/schedule/{mirror_id}")
    assert r.status_code == 403

    row = conn.execute(
        "SELECT id FROM schedule_item WHERE id = ?", (mirror_id,)
    ).fetchone()
    assert row is not None


async def test_patch_unknown_schedule_item(client):
    r = await client.patch("/api/schedule/99999", json={"notes": "nope"})
    assert r.status_code == 404
