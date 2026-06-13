from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from studio_app.db_lock import hold

router = APIRouter()

_PCT_FIELDS = ("x_pct", "y_pct", "w_pct", "h_pct")
_DEFAULT_COLOR = "#FFFF00"


def _mark_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "book_id": row["book_id"],
        "page": row["page"],
        "x_pct": row["x_pct"],
        "y_pct": row["y_pct"],
        "w_pct": row["w_pct"],
        "h_pct": row["h_pct"],
        "color": row["color"],
        "comment": row["comment"],
        "created_at": row["created_at"],
    }


def _validate_pct_fields(payload: dict) -> None:
    for field in _PCT_FIELDS:
        if field not in payload:
            raise HTTPException(400, f"{field} is required")
        value = payload[field]
        if not isinstance(value, (int, float)):
            raise HTTPException(400, f"{field} must be a number")
        if value < 0 or value > 100:
            raise HTTPException(400, f"{field} must be between 0 and 100")


def _book_slug(conn: sqlite3.Connection, book_id: int) -> str:
    row = conn.execute("SELECT slug FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    return row["slug"]


def _mirror_marks(conn: sqlite3.Connection, data_root: Path, book_id: int) -> None:
    slug = _book_slug(conn, book_id)
    book_dir = data_root / "books" / slug
    book_dir.mkdir(parents=True, exist_ok=True)
    marks_path = book_dir / "marks.json"

    rows = conn.execute(
        "SELECT * FROM mark WHERE book_id = ? ORDER BY page, created_at",
        (book_id,),
    ).fetchall()
    marks = [_mark_row_to_dict(r) for r in rows]

    tmp_path = book_dir / f".marks.json.{os.getpid()}.tmp"
    try:
        tmp_path.write_text(
            json.dumps(marks, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, marks_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


@router.get("/api/books/{book_id}/marks")
def list_marks(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    _book_slug(conn, book_id)
    rows = conn.execute(
        "SELECT * FROM mark WHERE book_id = ? ORDER BY page, created_at",
        (book_id,),
    ).fetchall()
    return {"marks": [_mark_row_to_dict(r) for r in rows]}


@router.post("/api/marks", status_code=201)
async def create_mark(request: Request) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")

    if "book_id" not in payload:
        raise HTTPException(400, "book_id is required")
    if "page" not in payload:
        raise HTTPException(400, "page is required")
    _validate_pct_fields(payload)

    book_id = payload["book_id"]
    if not isinstance(book_id, int):
        raise HTTPException(400, "book_id must be an integer")
    page = payload["page"]
    if not isinstance(page, int):
        raise HTTPException(400, "page must be an integer")

    _book_slug(conn, book_id)
    color = payload.get("color", _DEFAULT_COLOR)
    comment = payload.get("comment")

    with hold(request.app.state.db_lock):
        cur = conn.execute(
            "INSERT INTO mark (book_id, page, x_pct, y_pct, w_pct, h_pct, color, comment)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                book_id,
                page,
                payload["x_pct"],
                payload["y_pct"],
                payload["w_pct"],
                payload["h_pct"],
                color,
                comment,
            ),
        )
        row = conn.execute("SELECT * FROM mark WHERE id = ?", (cur.lastrowid,)).fetchone()
        _mirror_marks(conn, data_root, book_id)
    return _mark_row_to_dict(row)


@router.patch("/api/marks/{mark_id}")
async def patch_mark(mark_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    row = conn.execute("SELECT * FROM mark WHERE id = ?", (mark_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Mark not found")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")

    allowed = {"color", "comment"}
    unknown = set(payload.keys()) - allowed
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {sorted(unknown)}")
    if not payload:
        return _mark_row_to_dict(row)

    color = payload.get("color", row["color"])
    comment = payload.get("comment", row["comment"])
    with hold(request.app.state.db_lock):
        conn.execute(
            "UPDATE mark SET color = ?, comment = ? WHERE id = ?",
            (color, comment, mark_id),
        )
        row = conn.execute("SELECT * FROM mark WHERE id = ?", (mark_id,)).fetchone()
        _mirror_marks(conn, data_root, row["book_id"])
    return _mark_row_to_dict(row)


@router.delete("/api/marks/{mark_id}", status_code=204)
def delete_mark(mark_id: int, request: Request) -> Response:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    row = conn.execute("SELECT * FROM mark WHERE id = ?", (mark_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Mark not found")

    book_id = row["book_id"]
    with hold(request.app.state.db_lock):
        conn.execute("DELETE FROM mark WHERE id = ?", (mark_id,))
        _mirror_marks(conn, data_root, book_id)
    return Response(status_code=204)
