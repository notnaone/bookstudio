from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from studio_app.db_lock import hold

router = APIRouter()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _session_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "book_id": row["book_id"],
        "start_page": row["start_page"],
        "tracked_progress_page": row["tracked_progress_page"],
        "active_seconds": row["active_seconds"],
        "ended_at": row["ended_at"],
        "auto_closed": row["auto_closed"],
    }


@router.get("/api/reading_session/{session_id}")
def get_reading_session(session_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT * FROM reading_session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Session not found")
    return _session_row_to_dict(row)


@router.post("/api/reading_session", status_code=201)
async def create_reading_session(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    if "book_id" not in payload:
        raise HTTPException(400, "book_id is required")
    book_id = payload["book_id"]
    if not isinstance(book_id, int):
        raise HTTPException(400, "book_id must be an integer")

    schedule_item_id = payload.get("schedule_item_id")
    if schedule_item_id is not None and not isinstance(schedule_item_id, int):
        raise HTTPException(400, "schedule_item_id must be an integer")

    with hold(request.app.state.db_lock):
        book = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
        if book is None:
            raise HTTPException(404, "Book not found")

        existing = conn.execute(
            "SELECT * FROM reading_session"
            " WHERE book_id = ? AND ended_at IS NULL"
            " LIMIT 1",
            (book_id,),
        ).fetchone()
        if existing is not None:
            return _session_row_to_dict(existing)

        now = _utc_now()
        start_page = book["current_page"]
        cur = conn.execute(
            "INSERT INTO reading_session"
            " (book_id, narrator_id, started_at, start_page, tracked_progress_page,"
            " last_heartbeat_at, ended_at, schedule_item_id)"
            " VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
            (
                book_id,
                book["narrator_id"],
                now,
                start_page,
                start_page,
                now,
                schedule_item_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM reading_session WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
    return _session_row_to_dict(row)


@router.patch("/api/reading_session/{session_id}/heartbeat")
async def heartbeat(session_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")

    if "tracked_progress_page" not in payload:
        raise HTTPException(400, "tracked_progress_page is required")
    if "active_seconds_delta" not in payload:
        raise HTTPException(400, "active_seconds_delta is required")

    tracked_progress_page = payload["tracked_progress_page"]
    active_seconds_delta = payload["active_seconds_delta"]
    if not isinstance(tracked_progress_page, int):
        raise HTTPException(400, "tracked_progress_page must be an integer")
    if not isinstance(active_seconds_delta, int):
        raise HTTPException(400, "active_seconds_delta must be an integer")

    row = conn.execute(
        "SELECT * FROM reading_session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Session not found")

    now = _utc_now()
    with hold(request.app.state.db_lock):
        cur = conn.execute(
            "UPDATE reading_session"
            " SET tracked_progress_page = ?,"
            " active_seconds = active_seconds + ?,"
            " last_heartbeat_at = ?"
            " WHERE id = ? AND ended_at IS NULL",
            (tracked_progress_page, active_seconds_delta, now, session_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "Session already ended")
        conn.execute(
            "UPDATE book SET current_page = ? WHERE id = ?",
            (tracked_progress_page, row["book_id"]),
        )

    row = conn.execute(
        "SELECT * FROM reading_session WHERE id = ?", (session_id,)
    ).fetchone()
    return _session_row_to_dict(row)


@router.post("/api/reading_session/{session_id}/end")
async def end_session(session_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    raw = await request.body()
    if raw:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise HTTPException(400, "JSON object required")
    else:
        payload = {}

    row = conn.execute(
        "SELECT * FROM reading_session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Session not found")

    if row["ended_at"] is not None:
        return _session_row_to_dict(row)

    end_page = payload.get("end_page", row["tracked_progress_page"])
    if end_page is not None and not isinstance(end_page, int):
        raise HTTPException(400, "end_page must be an integer")

    now = _utc_now()
    if "active_seconds" in payload:
        active_seconds = payload["active_seconds"]
        if not isinstance(active_seconds, int):
            raise HTTPException(400, "active_seconds must be an integer")
        conn.execute(
            "UPDATE reading_session"
            " SET ended_at = ?, end_page = ?, active_seconds = ?"
            " WHERE id = ?",
            (now, end_page, active_seconds, session_id),
        )
    else:
        conn.execute(
            "UPDATE reading_session SET ended_at = ?, end_page = ? WHERE id = ?",
            (now, end_page, session_id),
        )

    row = conn.execute(
        "SELECT * FROM reading_session WHERE id = ?", (session_id,)
    ).fetchone()
    return _session_row_to_dict(row)
