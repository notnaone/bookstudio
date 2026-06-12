from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from studio_app.calendar_poller import CalendarPoller
from studio_app.main import build_app

FIXTURES = Path(__file__).parent / "fixtures"


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


def _seed_narrator(conn, name: str, alias: str) -> int:
    return conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES (?, ?)",
        (name, alias),
    ).lastrowid


def _seed_book(conn, *, narrator_id: int, title: str, status: str = "in_progress") -> int:
    slug = title.lower().replace(" ", "-")
    return conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, narrator_id, status)"
        " VALUES (?, ?, 'txt', '/x', '/x', ?, ?)",
        (slug, title, narrator_id, status),
    ).lastrowid


async def _seed_calendar_event(conn, *, title: str) -> int:
    return conn.execute(
        "INSERT INTO schedule_item"
        " (source, google_event_id, start_time, end_time, raw_title)"
        " VALUES ('studio_1', ?, '2026-06-21T10:00:00+00:00',"
        " '2026-06-21T12:00:00+00:00', ?)",
        (f"uid-{title}", title),
    ).lastrowid


async def test_start_session_case_a(client, conn):
    narr = _seed_narrator(conn, "Chris", "Chris")
    book_id = _seed_book(conn, narrator_id=narr, title="Chris Book")
    item_id = await _seed_calendar_event(conn, title="Chris - Session")

    r = await client.post(f"/api/schedule/{item_id}/start_session", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "A"
    assert body["book_id"] == book_id
    assert body["session_id"] > 0

    sched = conn.execute(
        "SELECT action_status, resolved_book_id FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    assert sched["action_status"] == "started"
    assert sched["resolved_book_id"] == book_id


async def test_start_session_case_b(client, conn):
    narr = _seed_narrator(conn, "Chris", "Chris")
    _seed_book(conn, narrator_id=narr, title="Book One")
    _seed_book(conn, narrator_id=narr, title="Book Two")
    item_id = await _seed_calendar_event(conn, title="Chris - Pick")

    r = await client.post(f"/api/schedule/{item_id}/start_session", json={})
    assert r.json()["mode"] == "B"
    assert len(r.json()["candidate_books"]) == 2


async def test_start_session_case_c(client, conn):
    item_id = await _seed_calendar_event(conn, title="Unknown Person")
    r = await client.post(f"/api/schedule/{item_id}/start_session", json={})
    assert r.json()["mode"] == "C"


async def test_start_session_longest_alias_wins(client, conn):
    _seed_narrator(conn, "Chris", "Chris")
    christina_id = _seed_narrator(conn, "Christina", "Christina")
    _seed_book(conn, narrator_id=christina_id, title="Christina Book")
    item_id = await _seed_calendar_event(conn, title="Christina - Bar")

    r = await client.post(f"/api/schedule/{item_id}/start_session", json={})
    body = r.json()
    assert body["mode"] == "A"
    sched = conn.execute(
        "SELECT resolved_narrator_id FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    assert sched["resolved_narrator_id"] == christina_id


async def test_schedule_refresh_with_poller(conn, data_root, local_state_dir):
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('data_root', ?),"
        " ('ics_url_studio_1', 'http://test/ics')",
        (str(data_root),),
    )
    poller = CalendarPoller(
        conn,
        interval_seconds=300,
        fetch_fn=lambda url: (FIXTURES / "sample.ics").read_bytes(),
        urls_provider=lambda c: {
            "studio_1": "http://test/ics",
            "studio_2": None,
        },
    )
    app = build_app(
        conn=conn,
        data_root=data_root,
        local_state_dir=local_state_dir,
        calendar_poller=poller,
        db_lock=threading.Lock(),
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/api/schedule/refresh")
        assert r.status_code == 200, r.text
        assert r.json()["synced_at"] is not None
        hb = await client.get("/api/heartbeat")
        assert hb.json()["last_calendar_sync_at"] is not None


async def test_jit_onboard_creates_book_and_session(client, conn, tmp_path: Path):
    item_id = await _seed_calendar_event(conn, title="New Voice - Pilot")
    sample = tmp_path / "jit.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            f"/api/schedule/{item_id}/jit",
            files={"file": ("jit.txt", fh, "text/plain")},
            data={
                "title": "JIT Book",
                "narrator_name": "New Voice",
                "link_future_events": "true",
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["book_id"] > 0
    assert body["session_id"] > 0
    book = conn.execute("SELECT is_draft, status FROM book WHERE id = ?", (body["book_id"],)).fetchone()
    assert book["is_draft"] == 1
    assert book["status"] == "in_progress"


async def test_schedule_and_settings_pages(client):
    r = await client.get("/schedule")
    assert r.status_code == 200
    assert "schedule-table" in r.text
    r = await client.get("/settings")
    assert r.status_code == 200
    assert "ics1" in r.text
