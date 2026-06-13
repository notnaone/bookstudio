from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from studio_app.exports import (
    export_audio_files_csv,
    export_books_csv,
    export_sessions_csv,
)

router = APIRouter()


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _stream_with_optional_save(
    rows: Iterator[str],
    *,
    save: bool,
    data_root: Path,
    scope: str,
) -> Iterator[str]:
    if not save:
        yield from rows
        return

    exports_dir = data_root / "exports"
    if not exports_dir.is_dir():
        if save:
            exports_dir.mkdir(parents=True, exist_ok=True)
        else:
            yield from rows
            return

    out_path = exports_dir / f"{scope}-{_utc_stamp()}.csv"
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        for line in rows:
            fh.write(line)
            yield line


@router.get("/api/export/books.csv")
def export_books(
    request: Request,
    status: str | None = None,
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    save: int = Query(0, ge=0, le=1),
) -> StreamingResponse:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    rows = export_books_csv(conn, status=status, from_date=from_, to_date=to)
    filename = f"books-{_utc_stamp()}.csv"
    return StreamingResponse(
        _stream_with_optional_save(
            rows, save=bool(save), data_root=data_root, scope="books"
        ),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/export/sessions.csv")
def export_sessions(
    request: Request,
    kind: str = "all",
    from_: str | None = Query(None, alias="from"),
    to: str | None = None,
    save: int = Query(0, ge=0, le=1),
) -> StreamingResponse:
    if kind not in {"all", "reading", "recording", "editing"}:
        raise HTTPException(400, "kind must be all, reading, recording, or editing")
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    rows = export_sessions_csv(conn, kind=kind, from_date=from_, to_date=to)
    filename = f"sessions-{_utc_stamp()}.csv"
    return StreamingResponse(
        _stream_with_optional_save(
            rows, save=bool(save), data_root=data_root, scope="sessions"
        ),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/export/audio_files.csv")
def export_audio_files(
    request: Request,
    book_id: int | None = None,
    save: int = Query(0, ge=0, le=1),
) -> StreamingResponse:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root
    rows = export_audio_files_csv(conn, book_id=book_id)
    filename = f"audio_files-{_utc_stamp()}.csv"
    return StreamingResponse(
        _stream_with_optional_save(
            rows, save=bool(save), data_root=data_root, scope="audio_files"
        ),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/api/export/cleanup")
async def cleanup_exports(request: Request) -> dict:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    older_than_days = payload.get("older_than_days")
    if type(older_than_days) is not int or older_than_days < 0:
        raise HTTPException(400, "older_than_days must be a non-negative integer")

    exports_dir = request.app.state.data_root / "exports"
    if not exports_dir.is_dir():
        return {"deleted": 0}

    cutoff = time.time() - older_than_days * 86400
    deleted = 0
    for path in exports_dir.glob("*.csv"):
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
        except OSError:
            continue
    return {"deleted": deleted}
