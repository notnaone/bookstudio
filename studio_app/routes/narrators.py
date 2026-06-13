from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request

from studio_app.db_lock import hold

router = APIRouter()


def _row(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "calendar_alias": r["calendar_alias"],
        "notes": r["notes"],
        "created_at": r["created_at"],
    }


def _stats_for_narrator(conn, narrator_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM narrator_stats WHERE narrator_id = ?", (narrator_id,)
    ).fetchone()
    if row is None:
        return {
            "books_assigned": 0,
            "books_done": 0,
            "total_audio_seconds": 0,
            "avg_chars_per_hour": 0,
            "avg_pages_per_hour": 0,
        }
    return {
        "books_assigned": row["books_assigned"],
        "books_done": row["books_done"],
        "total_audio_seconds": row["total_audio_seconds"],
        "avg_chars_per_hour": row["avg_chars_per_hour"],
        "avg_pages_per_hour": row["avg_pages_per_hour"],
    }


def _upcoming_sessions(conn, narrator_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, source, start_time, end_time, raw_title, action_status"
        " FROM schedule_item"
        " WHERE resolved_narrator_id = ?"
        " AND julianday(start_time) > julianday('now')"
        " ORDER BY start_time",
        (narrator_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "source": r["source"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "raw_title": r["raw_title"],
            "action_status": r["action_status"],
        }
        for r in rows
    ]


def _history_for_narrator(conn, narrator_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT nb.book_id, b.title, nb.assigned_at, nb.finished_at"
        " FROM narrator_book nb"
        " JOIN book b ON b.id = nb.book_id"
        " WHERE nb.narrator_id = ?"
        " ORDER BY nb.assigned_at DESC",
        (narrator_id,),
    ).fetchall()
    return [
        {
            "book_id": r["book_id"],
            "title": r["title"],
            "assigned_at": r["assigned_at"],
            "finished_at": r["finished_at"],
        }
        for r in rows
    ]


@router.get("/api/narrators")
def list_narrators(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute("SELECT * FROM narrator ORDER BY name").fetchall()
    return {"narrators": [_row(r) for r in rows]}


@router.get("/api/narrators/{nid}")
def get_narrator(nid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Narrator not found")
    body = _row(row)
    body["stats"] = _stats_for_narrator(conn, nid)
    body["history"] = _history_for_narrator(conn, nid)
    body["upcoming_sessions"] = _upcoming_sessions(conn, nid)
    return body


@router.post("/api/narrators", status_code=201)
async def create_narrator(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name must be non-empty")
    alias = payload.get("calendar_alias")
    if alias is not None:
        alias = alias.strip() or None
    notes = payload.get("notes")
    try:
        with hold(request.app.state.db_lock):
            cur = conn.execute(
                "INSERT INTO narrator (name, calendar_alias, notes) VALUES (?, ?, ?)",
                (name, alias, notes),
            )
            row = conn.execute(
                "SELECT * FROM narrator WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"calendar_alias must be unique: {exc}") from exc
    return _row(row)


@router.patch("/api/narrators/{nid}")
async def patch_narrator(nid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Narrator not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = row["name"]
    alias = row["calendar_alias"]
    notes = row["notes"]
    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            raise HTTPException(400, "name must be non-empty")
        name = new_name
    if "calendar_alias" in payload:
        v = payload["calendar_alias"]
        if v is None:
            alias = None
        else:
            v = v.strip()
            alias = v or None
    if "notes" in payload:
        notes = payload["notes"]
    try:
        with hold(request.app.state.db_lock):
            conn.execute(
                "UPDATE narrator SET name = ?, calendar_alias = ?, notes = ? WHERE id = ?",
                (name, alias, notes, nid),
            )
            row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"calendar_alias must be unique: {exc}") from exc
    return _row(row)
