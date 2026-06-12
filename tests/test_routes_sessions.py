from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def _upload_book(client, tmp_path: Path, *, title: str = "Session Book") -> dict:
    sample = tmp_path / "upload.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("upload.txt", fh, "text/plain")},
            data={"title": title},
        )
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_session_sets_start_page_from_book(
    client, conn, tmp_path: Path
):
    book = await _upload_book(client, tmp_path)
    book_id = book["id"]
    conn.execute("UPDATE book SET current_page = 7 WHERE id = ?", (book_id,))

    r = await client.post(
        "/api/reading_session",
        json={"book_id": book_id},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["book_id"] == book_id
    assert body["start_page"] == 7
    assert body["tracked_progress_page"] == 7
    assert body["active_seconds"] == 0
    assert body["ended_at"] is None
    assert body["auto_closed"] == 0


async def test_heartbeat_updates_tracked_page_and_book(client, conn, tmp_path: Path):
    book = await _upload_book(client, tmp_path)
    book_id = book["id"]
    conn.execute("UPDATE book SET current_page = 3 WHERE id = ?", (book_id,))

    r = await client.post("/api/reading_session", json={"book_id": book_id})
    assert r.status_code == 201
    session_id = r.json()["id"]

    r = await client.patch(
        f"/api/reading_session/{session_id}/heartbeat",
        json={"tracked_progress_page": 5, "active_seconds_delta": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tracked_progress_page"] == 5
    assert body["active_seconds"] == 10
    assert body["ended_at"] is None

    row = conn.execute(
        "SELECT current_page FROM book WHERE id = ?", (book_id,)
    ).fetchone()
    assert row["current_page"] == 5


async def test_heartbeat_on_closed_session_returns_409(
    client, conn, tmp_path: Path
):
    book = await _upload_book(client, tmp_path)
    r = await client.post(
        "/api/reading_session",
        json={"book_id": book["id"]},
    )
    session_id = r.json()["id"]
    conn.execute(
        "UPDATE reading_session SET ended_at = '2026-01-01T00:00:00+00:00' WHERE id = ?",
        (session_id,),
    )

    r = await client.patch(
        f"/api/reading_session/{session_id}/heartbeat",
        json={"tracked_progress_page": 2, "active_seconds_delta": 1},
    )
    assert r.status_code == 409


async def test_heartbeat_after_reaper_close_does_not_update_row(
    client, conn, tmp_path: Path
):
    book = await _upload_book(client, tmp_path)
    r = await client.post(
        "/api/reading_session",
        json={"book_id": book["id"]},
    )
    session_id = r.json()["id"]
    conn.execute(
        "UPDATE reading_session SET ended_at = '2026-06-12T10:00:00+00:00',"
        " auto_closed = 1, last_heartbeat_at = '2026-06-12T09:00:00+00:00'"
        " WHERE id = ?",
        (session_id,),
    )

    r = await client.patch(
        f"/api/reading_session/{session_id}/heartbeat",
        json={"tracked_progress_page": 99, "active_seconds_delta": 50},
    )
    assert r.status_code == 409

    row = conn.execute(
        "SELECT tracked_progress_page, active_seconds, last_heartbeat_at"
        " FROM reading_session WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["tracked_progress_page"] != 99
    assert row["active_seconds"] != 50
    assert row["last_heartbeat_at"] == "2026-06-12T09:00:00+00:00"


async def test_end_session_idempotent(client, tmp_path: Path):
    book = await _upload_book(client, tmp_path)
    r = await client.post(
        "/api/reading_session",
        json={"book_id": book["id"]},
    )
    session_id = r.json()["id"]

    r = await client.post(
        f"/api/reading_session/{session_id}/end",
        json={"end_page": 4, "active_seconds": 120},
    )
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["ended_at"] is not None
    assert first["active_seconds"] == 120

    r = await client.post(f"/api/reading_session/{session_id}/end", json={})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["id"] == first["id"]
    assert second["ended_at"] == first["ended_at"]
    assert second["active_seconds"] == first["active_seconds"]
