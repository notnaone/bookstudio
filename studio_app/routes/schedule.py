from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from studio_app.db_lock import hold
from studio_app.ingest import ingest_book

router = APIRouter()

VALID_SOURCES = {"studio_1", "studio_2", "manual"}
VALID_KINDS = {"recording", "editing", "deadline"}
VALID_ACTION_STATUSES = {"pending", "started", "completed", "skipped", "cancelled"}
MIRROR_IMMUTABLE_FIELDS = {"raw_title", "start_time", "end_time", "source", "google_event_id"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "source": row["source"],
        "google_event_id": row["google_event_id"],
        "start_time": row["start_time"],
        "end_time": row["end_time"],
        "raw_title": row["raw_title"],
        "notes": row["notes"],
        "resolved_narrator_id": row["resolved_narrator_id"],
        "resolved_book_id": row["resolved_book_id"],
        "resolved_at": row["resolved_at"],
        "action_status": row["action_status"],
        "kind": row["kind"],
        "last_synced_at": row["last_synced_at"],
        "resolved_book_title": row["resolved_book_title"],
        "resolved_narrator_name": row["resolved_narrator_name"],
    }


def _select_sql() -> str:
    return (
        "SELECT si.*,"
        " b.title AS resolved_book_title,"
        " n.name AS resolved_narrator_name"
        " FROM schedule_item si"
        " LEFT JOIN book b ON b.id = si.resolved_book_id"
        " LEFT JOIN narrator n ON n.id = si.resolved_narrator_id"
    )


def _get_item(conn, item_id: int):
    return conn.execute(
        f"{_select_sql()} WHERE si.id = ?",
        (item_id,),
    ).fetchone()


def _require_enum(value: str, allowed: set[str], field: str) -> None:
    if value not in allowed:
        raise HTTPException(400, f"{field} must be one of: {', '.join(sorted(allowed))}")


@router.get("/api/schedule")
def list_schedule(
    request: Request,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    source: str | None = None,
) -> dict:
    conn = request.app.state.conn
    sql = f"{_select_sql()} WHERE 1=1"
    params: list[object] = []
    if from_ is not None:
        sql += " AND si.start_time >= ?"
        params.append(from_)
    if to is not None:
        sql += " AND si.start_time <= ?"
        params.append(to)
    if source is not None:
        _require_enum(source, VALID_SOURCES, "source")
        sql += " AND si.source = ?"
        params.append(source)
    sql += " ORDER BY si.start_time"
    rows = conn.execute(sql, params).fetchall()
    return {"items": [_row_to_dict(r) for r in rows]}


@router.post("/api/schedule", status_code=201)
async def create_schedule_item(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")

    if payload.get("google_event_id") is not None:
        raise HTTPException(400, "google_event_id is not allowed on manual rows")

    source = payload.get("source")
    if source != "manual":
        raise HTTPException(400, "source must be 'manual' for POST /api/schedule")

    kind = payload.get("kind")
    if kind is None:
        raise HTTPException(400, "kind is required for manual rows")
    _require_enum(kind, VALID_KINDS, "kind")

    for field in ("start_time", "end_time", "raw_title"):
        if not payload.get(field):
            raise HTTPException(400, f"{field} is required")

    start_time = payload["start_time"]
    end_time = payload["end_time"]
    raw_title = payload["raw_title"]
    notes = payload.get("notes")

    cur = conn.execute(
        "INSERT INTO schedule_item"
        " (source, google_event_id, start_time, end_time, raw_title, notes, kind)"
        " VALUES ('manual', NULL, ?, ?, ?, ?, ?)",
        (start_time, end_time, raw_title, notes, kind),
    )
    row = _get_item(conn, cur.lastrowid)
    assert row is not None
    return _row_to_dict(row)


@router.patch("/api/schedule/{item_id}")
async def patch_schedule_item(item_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    if not payload:
        raise HTTPException(400, "No fields to update")

    row = _get_item(conn, item_id)
    if row is None:
        raise HTTPException(404, "Schedule item not found")

    is_mirror = row["google_event_id"] is not None
    if is_mirror:
        forbidden = MIRROR_IMMUTABLE_FIELDS.intersection(payload.keys())
        if forbidden:
            raise HTTPException(
                400,
                f"Cannot modify calendar-mirrored fields: {', '.join(sorted(forbidden))}",
            )

    updates: dict[str, object] = {}
    if "action_status" in payload:
        status = payload["action_status"]
        _require_enum(status, VALID_ACTION_STATUSES, "action_status")
        updates["action_status"] = status
    if "kind" in payload:
        kind = payload["kind"]
        if kind is not None:
            _require_enum(kind, VALID_KINDS, "kind")
        updates["kind"] = kind
    if "notes" in payload:
        updates["notes"] = payload["notes"]
    if not is_mirror:
        for field in ("raw_title", "start_time", "end_time"):
            if field in payload:
                if not payload[field]:
                    raise HTTPException(400, f"{field} cannot be empty")
                updates[field] = payload[field]

    resolved_changed = False
    if "resolved_narrator_id" in payload:
        narrator_id = payload["resolved_narrator_id"]
        if narrator_id is not None:
            if conn.execute(
                "SELECT id FROM narrator WHERE id = ?", (narrator_id,)
            ).fetchone() is None:
                raise HTTPException(404, "Narrator not found")
        updates["resolved_narrator_id"] = narrator_id
        resolved_changed = True
    if "resolved_book_id" in payload:
        book_id = payload["resolved_book_id"]
        if book_id is not None:
            if conn.execute(
                "SELECT id FROM book WHERE id = ?", (book_id,)
            ).fetchone() is None:
                raise HTTPException(404, "Book not found")
        updates["resolved_book_id"] = book_id
        resolved_changed = True

    if resolved_changed:
        updates["resolved_at"] = _utc_now()

    if not updates:
        raise HTTPException(400, "No valid fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(
        f"UPDATE schedule_item SET {set_clause} WHERE id = ?",
        (*updates.values(), item_id),
    )
    row = _get_item(conn, item_id)
    assert row is not None
    return _row_to_dict(row)


@router.delete("/api/schedule/{item_id}", status_code=204)
def delete_schedule_item(item_id: int, request: Request) -> None:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT id, google_event_id FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Schedule item not found")
    if row["google_event_id"] is not None:
        raise HTTPException(403, "Calendar-mirrored rows cannot be deleted")
    conn.execute("DELETE FROM schedule_item WHERE id = ?", (item_id,))


@router.post("/api/schedule/refresh")
def refresh_schedule(request: Request) -> dict:
    conn = request.app.state.conn
    poller = getattr(request.app.state, "calendar_poller", None)
    if poller is None:
        raise HTTPException(503, "Calendar poller not configured")
    before = conn.execute("SELECT COUNT(*) AS c FROM schedule_item").fetchone()["c"]
    poller.poll_once()
    after = conn.execute("SELECT COUNT(*) AS c FROM schedule_item").fetchone()["c"]
    return {
        "synced_at": poller.last_sync_at,
        "items_upserted": max(0, after - before),
    }


def resolve_narrator_from_title(conn, raw_title: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM narrator"
        " WHERE calendar_alias IS NOT NULL"
        " AND LOWER(?) LIKE LOWER(calendar_alias) || '%'"
        " ORDER BY LENGTH(calendar_alias) DESC"
        " LIMIT 1",
        (raw_title,),
    ).fetchone()
    return int(row["id"]) if row else None


def _candidate_books(conn, narrator_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title FROM book"
        " WHERE narrator_id = ? AND status = 'in_progress'"
        " ORDER BY title",
        (narrator_id,),
    ).fetchall()
    return [{"id": r["id"], "title": r["title"]} for r in rows]


def _assign_narrator_to_book(conn, book_id: int, narrator_id: int) -> None:
    conn.execute(
        "UPDATE book SET narrator_id = ? WHERE id = ?",
        (narrator_id, book_id),
    )
    conn.execute(
        "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)"
        " ON CONFLICT(narrator_id, book_id) DO UPDATE SET"
        " finished_at = NULL, assigned_at = CURRENT_TIMESTAMP",
        (narrator_id, book_id),
    )


def _open_session_for_schedule(conn, schedule_item_id: int):
    return conn.execute(
        "SELECT id, book_id FROM reading_session"
        " WHERE schedule_item_id = ? AND ended_at IS NULL"
        " LIMIT 1",
        (schedule_item_id,),
    ).fetchone()


def _insert_reading_session(
    conn, book_id: int, schedule_item_id: int
) -> int:
    book = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if book is None:
        raise HTTPException(404, "Book not found")
    now = _utc_now()
    cur = conn.execute(
        "INSERT INTO reading_session"
        " (book_id, narrator_id, started_at, start_page, tracked_progress_page,"
        " last_heartbeat_at, ended_at, schedule_item_id)"
        " VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
        (
            book_id,
            book["narrator_id"],
            now,
            book["current_page"],
            book["current_page"],
            now,
            schedule_item_id,
        ),
    )
    return int(cur.lastrowid)


def _start_case_a(
    conn, item_id: int, narrator_id: int, book_id: int
) -> dict:
    existing = _open_session_for_schedule(conn, item_id)
    if existing is not None:
        return {
            "mode": "A",
            "session_id": int(existing["id"]),
            "book_id": int(existing["book_id"]),
        }
    now = _utc_now()
    session_id = _insert_reading_session(conn, book_id, item_id)
    conn.execute(
        "UPDATE schedule_item"
        " SET resolved_narrator_id = ?, resolved_book_id = ?,"
        " resolved_at = ?, action_status = 'started'"
        " WHERE id = ?",
        (narrator_id, book_id, now, item_id),
    )
    return {"mode": "A", "session_id": session_id, "book_id": book_id}


@router.post("/api/schedule/{item_id}/start_session")
async def start_session(item_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = _get_item(conn, item_id)
    if row is None:
        raise HTTPException(404, "Schedule item not found")

    raw = await request.body()
    payload: dict = {}
    if raw:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise HTTPException(400, "JSON object required")

    book_id = payload.get("book_id")
    if book_id is not None and not isinstance(book_id, int):
        raise HTTPException(400, "book_id must be an integer")

    narrator_id = resolve_narrator_from_title(conn, row["raw_title"])
    if narrator_id is None:
        return {"mode": "C", "raw_title": row["raw_title"]}

    candidates = _candidate_books(conn, narrator_id)
    if not candidates:
        return {"mode": "C", "raw_title": row["raw_title"]}

    if book_id is not None:
        if not any(c["id"] == book_id for c in candidates):
            raise HTTPException(400, "book_id is not an in-progress book for this narrator")
        with hold(request.app.state.db_lock):
            return _start_case_a(conn, item_id, narrator_id, book_id)

    if len(candidates) == 1:
        with hold(request.app.state.db_lock):
            return _start_case_a(conn, item_id, narrator_id, candidates[0]["id"])

    return {
        "mode": "B",
        "narrator_id": narrator_id,
        "candidate_books": candidates,
    }


@router.post("/api/schedule/{item_id}/jit", status_code=201)
async def jit_onboard(
    item_id: int,
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    narrator_id: int | None = Form(None),
    narrator_name: str | None = Form(None),
    calendar_alias: str | None = Form(None),
    link_future_events: str | None = Form(None),
    audio_folder: str | None = Form(None),
) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    row = _get_item(conn, item_id)
    if row is None:
        raise HTTPException(404, "Schedule item not found")

    if narrator_id is None and not (narrator_name or "").strip():
        raise HTTPException(400, "narrator_id or narrator_name is required")

    suffix = Path(file.filename or "").suffix or ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        try:
            book_id = ingest_book(
                conn,
                data_root,
                tmp_path,
                title=title.strip(),
                audio_folder=audio_folder or None,
                is_draft=True,
                original_filename=file.filename or None,
            )
        except ValueError as exc:
            raise HTTPException(400, f"Unsupported file: {exc}") from exc

        with hold(request.app.state.db_lock):
            existing = _open_session_for_schedule(conn, item_id)
            if existing is not None:
                book_id = int(existing["book_id"])
                narr_row = conn.execute(
                    "SELECT narrator_id FROM book WHERE id = ?", (book_id,)
                ).fetchone()
                narr_id = (
                    int(narr_row["narrator_id"])
                    if narr_row and narr_row["narrator_id"] is not None
                    else None
                )
                return {
                    "session_id": int(existing["id"]),
                    "book_id": book_id,
                    "narrator_id": narr_id,
                }

            if narrator_id is not None:
                narr = conn.execute(
                    "SELECT id FROM narrator WHERE id = ?", (narrator_id,)
                ).fetchone()
                if narr is None:
                    raise HTTPException(404, "Narrator not found")
                resolved_narrator_id = narrator_id
            else:
                should_link = str(link_future_events or "").lower() in {
                    "true", "1", "on", "yes",
                }
                alias = calendar_alias
                if should_link and not alias:
                    alias = narrator_name
                try:
                    cur = conn.execute(
                        "INSERT INTO narrator (name, calendar_alias)"
                        " VALUES (?, ?)",
                        (narrator_name.strip(), alias),
                    )
                except sqlite3.IntegrityError as exc:
                    raise HTTPException(
                        400, f"calendar_alias must be unique: {exc}"
                    ) from exc
                resolved_narrator_id = int(cur.lastrowid)

            _assign_narrator_to_book(conn, book_id, resolved_narrator_id)
            conn.execute(
                "UPDATE book SET status = 'in_progress' WHERE id = ?",
                (book_id,),
            )
            session_id = _insert_reading_session(conn, book_id, item_id)
            now = _utc_now()
            conn.execute(
                "UPDATE schedule_item"
                " SET resolved_narrator_id = ?, resolved_book_id = ?,"
                " resolved_at = ?, action_status = 'started'"
                " WHERE id = ?",
                (resolved_narrator_id, book_id, now, item_id),
            )
    finally:
        try:
            tmp_path.unlink()
        except (FileNotFoundError, PermissionError, OSError):
            pass

    return {
        "session_id": session_id,
        "book_id": book_id,
        "narrator_id": resolved_narrator_id,
    }
