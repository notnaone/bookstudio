from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

router = APIRouter()


def _view_page_response(book_id: int, page: int, request: Request) -> FileResponse:
    conn = request.app.state.conn
    row = conn.execute("SELECT view_path FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    view_path = row["view_path"]
    if not view_path:
        raise HTTPException(404, "No view path")
    view_dir = Path(view_path)
    if not view_dir.is_dir():
        raise HTTPException(404, "Book has no paginated view")
    target = view_dir / f"page-{page:04d}.html"
    if not target.is_file():
        raise HTTPException(404, "Page not found")
    return FileResponse(target, media_type="text/html")


@router.get("/api/books/{book_id}/view/page-{page}.html")
def get_view_page(book_id: int, page: int, request: Request) -> FileResponse:
    return _view_page_response(book_id, page, request)


@router.head("/api/books/{book_id}/view/page-{page}.html")
def head_view_page(book_id: int, page: int, request: Request) -> FileResponse:
    return _view_page_response(book_id, page, request)


@router.get("/api/books/{book_id}/view/source")
def get_view_source(book_id: int, request: Request) -> FileResponse:
    conn = request.app.state.conn
    row = conn.execute("SELECT source_path FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    src = Path(row["source_path"])
    if not src.is_file():
        raise HTTPException(404, "Source file not found")
    return FileResponse(src)
