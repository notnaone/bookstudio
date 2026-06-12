from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request

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
