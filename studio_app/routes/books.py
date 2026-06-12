from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from studio_app.ingest import ingest_book

router = APIRouter()


def _book_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "format": row["format"],
        "body_chars": row["body_chars"],
        "raw_chars": row["raw_chars"],
        "chars_per_page": row["chars_per_page"],
        "pages": row["pages"],
        "images": row["images"],
        "charts_tables": row["charts_tables"],
        "status": row["status"],
        "is_draft": row["is_draft"],
        "current_page": row["current_page"],
        "publisher_id": row["publisher_id"],
        "narrator_id": row["narrator_id"],
        "genre": row["genre"],
        "publisher_notes": row["publisher_notes"],
        "planned_end": row["planned_end"],
        "audio_folder": row["audio_folder"],
        "drive_sync_path": row["drive_sync_path"],
        "source_path": row["source_path"],
        "view_path": row["view_path"],
    }


@router.get("/api/books")
def list_books(
    request: Request,
    status: str | None = None,
    narrator_id: int | None = None,
    publisher_id: int | None = None,
    q: str | None = None,
) -> dict:
    conn = request.app.state.conn
    clauses: list[str] = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if narrator_id is not None:
        clauses.append("narrator_id = ?")
        params.append(narrator_id)
    if publisher_id is not None:
        clauses.append("publisher_id = ?")
        params.append(publisher_id)
    if q:
        clauses.append("title LIKE ?")
        params.append(f"%{q}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM book {where} ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return {"books": [_book_row_to_dict(r) for r in rows]}


@router.get("/api/books/{book_id}")
def get_book(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return _book_row_to_dict(row)


@router.post("/api/books", status_code=201)
async def create_book(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root

    suffix = Path(file.filename or "").suffix or ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        book_id = ingest_book(
            conn, data_root, tmp_path, title=title,
            original_filename=file.filename or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported file: {exc}") from exc
    finally:
        try:
            tmp_path.unlink()
        except (FileNotFoundError, PermissionError, OSError):
            # On Windows the parser may still hold a handle; OS cleans up on GC.
            pass

    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)


_PATCHABLE_FIELDS = {
    "status", "genre", "publisher_notes", "planned_end",
    "publisher_id", "narrator_id",
    "audio_folder", "drive_sync_path",
    "is_draft",
}
_ALLOWED_STATUS = {"planned", "in_progress", "done", "archived"}


@router.patch("/api/books/{book_id}")
async def patch_book(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    unknown = set(payload.keys()) - _PATCHABLE_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {sorted(unknown)}")
    updates: dict = {}
    if "status" in payload:
        if payload["status"] not in _ALLOWED_STATUS:
            raise HTTPException(
                400, f"status must be one of {sorted(_ALLOWED_STATUS)}"
            )
        updates["status"] = payload["status"]
    if "is_draft" in payload:
        wants_draft = bool(payload["is_draft"])
        if not wants_draft:
            new_publisher = payload.get("publisher_id", row["publisher_id"])
            new_genre = payload.get("genre", row["genre"])
            if new_publisher is None or not (new_genre or "").strip():
                raise HTTPException(
                    400,
                    "Cannot clear draft: publisher_id and genre must be set first",
                )
        updates["is_draft"] = 1 if wants_draft else 0
    for fld in (
        "genre", "publisher_notes", "planned_end",
        "publisher_id", "narrator_id", "audio_folder", "drive_sync_path",
    ):
        if fld in payload:
            updates[fld] = payload[fld]
    if not updates:
        return _book_row_to_dict(row)
    cols = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [book_id]
    conn.execute(f"UPDATE book SET {cols} WHERE id = ?", params)
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)
