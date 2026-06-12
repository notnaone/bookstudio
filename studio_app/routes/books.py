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
        "planned_end": row["planned_end"],
        "audio_folder": row["audio_folder"],
        "source_path": row["source_path"],
        "view_path": row["view_path"],
    }


@router.get("/api/books")
def list_books(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute(
        "SELECT * FROM book ORDER BY updated_at DESC"
    ).fetchall()
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
        chunk = await file.read()
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
        except FileNotFoundError:
            pass

    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)
