from __future__ import annotations

import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from studio_app.db_lock import hold
from studio_app.ingest import ingest_book
from studio_app.source_fetch import download_source

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


def _stats_for_book(conn, book_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM book_stats WHERE book_id = ?", (book_id,)
    ).fetchone()
    if row is None:
        return {
            "total_audio_seconds": 0,
            "chars_per_hour": 0,
            "pages_per_hour": 0,
            "progress_pct": 0,
        }
    return {
        "total_audio_seconds": row["total_audio_seconds"],
        "chars_per_hour": row["chars_per_hour"],
        "pages_per_hour": row["pages_per_hour"],
        "progress_pct": row["progress_pct"],
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
    body = _book_row_to_dict(row)
    body["stats"] = _stats_for_book(conn, book_id)
    return body


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
        with hold(request.app.state.db_lock):
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
            pass

    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)


class BookFromUrlBody(BaseModel):
    url: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)


@router.post("/api/books/from_url", status_code=201)
async def create_book_from_url(request: Request, body: BookFromUrlBody) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root

    try:
        tmp_path = download_source(body.url)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except requests.HTTPError as exc:
        raise HTTPException(
            status_code=400, detail=f"Download failed: {exc}"
        ) from exc

    try:
        with hold(request.app.state.db_lock):
            book_id = ingest_book(
                conn,
                data_root,
                tmp_path,
                title=body.title.strip(),
                original_filename=tmp_path.name,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported file: {exc}") from exc
    finally:
        try:
            tmp_path.unlink()
        except (FileNotFoundError, PermissionError, OSError):
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
_TERMINAL_STATUS = {"done", "archived"}


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

    with hold(request.app.state.db_lock):
        conn.execute("SAVEPOINT patch_book")
        try:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            new_narr = updates.get("narrator_id", row["narrator_id"])
            old_narr = row["narrator_id"]
            if "narrator_id" in updates and new_narr != old_narr:
                if old_narr is not None:
                    conn.execute(
                        "UPDATE narrator_book SET finished_at = ?"
                        " WHERE book_id = ? AND narrator_id = ? AND finished_at IS NULL",
                        (now, book_id, old_narr),
                    )
                if new_narr is not None:
                    conn.execute(
                        "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)"
                        " ON CONFLICT(narrator_id, book_id) DO UPDATE SET"
                        " finished_at = NULL, assigned_at = CURRENT_TIMESTAMP",
                        (new_narr, book_id),
                    )

            if "status" in updates:
                new_status = updates["status"]
                old_status = row["status"]
                narr = updates.get("narrator_id", row["narrator_id"])
                if new_status != old_status and narr is not None:
                    if new_status in _TERMINAL_STATUS:
                        conn.execute(
                            "UPDATE narrator_book SET finished_at = ?"
                            " WHERE book_id = ? AND narrator_id = ?"
                            " AND finished_at IS NULL",
                            (now, book_id, narr),
                        )
                    elif old_status in _TERMINAL_STATUS and new_status in (
                        "planned", "in_progress"
                    ):
                        conn.execute(
                            "UPDATE narrator_book SET finished_at = NULL"
                            " WHERE book_id = ? AND narrator_id = ?",
                            (book_id, narr),
                        )

            cols = ", ".join(f"{k} = ?" for k in updates)
            params = list(updates.values()) + [book_id]
            conn.execute(f"UPDATE book SET {cols} WHERE id = ?", params)
            conn.execute("RELEASE SAVEPOINT patch_book")
        except sqlite3.IntegrityError as exc:
            conn.execute("ROLLBACK TO SAVEPOINT patch_book")
            conn.execute("RELEASE SAVEPOINT patch_book")
            raise HTTPException(400, f"Foreign key constraint failed: {exc}") from exc
        except Exception:
            conn.execute("ROLLBACK TO SAVEPOINT patch_book")
            conn.execute("RELEASE SAVEPOINT patch_book")
            raise

        if "audio_folder" in updates:
            from studio_app.audio_scanner import recompute_stats, scan_book
            scan_book(conn, book_id)
            recompute_stats(conn)

    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)


@router.patch("/api/books/{book_id}/active_page")
async def patch_active_page(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    payload = await request.json()
    if not isinstance(payload, dict) or "tracked_progress_page" not in payload:
        raise HTTPException(400, "tracked_progress_page required")
    page = int(payload["tracked_progress_page"])
    if page < 1:
        raise HTTPException(400, "tracked_progress_page must be >= 1")
    if row["pages"] and page > int(row["pages"]):
        raise HTTPException(400, "tracked_progress_page exceeds book.pages")
    with hold(request.app.state.db_lock):
        conn.execute(
            "UPDATE book SET current_page = ? WHERE id = ?",
            (page, book_id),
        )
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)


@router.delete("/api/books/{book_id}", status_code=204)
def delete_book(book_id: int, request: Request) -> None:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")

    with hold(request.app.state.db_lock):
        conn.execute("DELETE FROM mark WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM audio_file WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM book_stats WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM narrator_book WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM reading_session WHERE book_id = ?", (book_id,))
        conn.execute("DELETE FROM work_session WHERE book_id = ?", (book_id,))
        conn.execute(
            "UPDATE schedule_item SET resolved_book_id = NULL"
            " WHERE resolved_book_id = ?",
            (book_id,),
        )
        conn.execute("DELETE FROM book WHERE id = ?", (book_id,))

    book_dir = data_root / "books" / row["slug"]
    if book_dir.is_dir():
        shutil.rmtree(book_dir, ignore_errors=True)

    from studio_app.audio_scanner import recompute_stats
    with hold(request.app.state.db_lock):
        recompute_stats(conn)


@router.post("/api/books/{book_id}/rescan_audio")
def rescan_audio(book_id: int, request: Request) -> dict:
    from studio_app.audio_scanner import recompute_stats, scan_book
    conn = request.app.state.conn
    row = conn.execute("SELECT id FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    with hold(request.app.state.db_lock):
        count = scan_book(conn, book_id)
        recompute_stats(conn)
    return {"book_id": book_id, "audio_files": count}
