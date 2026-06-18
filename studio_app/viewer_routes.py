from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
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


_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return unescape(_TAG_RE.sub(" ", html))


@router.get("/api/books/{book_id}/search")
def search_book_content(
    book_id: int,
    request: Request,
    q: str = Query(..., min_length=1),
    limit: int = Query(200, ge=1, le=500),
) -> dict:
    """Search paginated HTML view files; return every match with page and index."""
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT view_path, format, pages FROM book WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")

    needle = q.casefold()
    matches: list[dict] = []
    view_path = row["view_path"]
    if not view_path:
        return {"total": 0, "matches": [], "truncated": False}

    view_dir = Path(view_path)
    if view_dir.is_dir():
        for page_file in sorted(view_dir.glob("page-*.html")):
            stem = page_file.stem
            try:
                page_num = int(stem.split("-", 1)[1])
            except (IndexError, ValueError):
                continue
            text = _strip_html(page_file.read_text(encoding="utf-8", errors="replace"))
            text_fold = text.casefold()
            start = 0
            index_on_page = 0
            while True:
                idx = text_fold.find(needle, start)
                if idx == -1:
                    break
                snippet_start = max(0, idx - 40)
                snippet_end = min(len(text), idx + len(q) + 40)
                matches.append({
                    "page": page_num,
                    "index_on_page": index_on_page,
                    "global_index": len(matches),
                    "snippet": text[snippet_start:snippet_end].strip(),
                })
                index_on_page += 1
                start = idx + len(needle)
                if len(matches) >= limit:
                    break
            if len(matches) >= limit:
                break
    truncated = len(matches) >= limit
    return {"total": len(matches), "matches": matches, "truncated": truncated}


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
