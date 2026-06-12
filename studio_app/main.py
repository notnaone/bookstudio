from __future__ import annotations

import sqlite3
import sys
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from studio_app.db import connect, migrate
from studio_app.routes import books as books_routes
from studio_app.routes import settings_routes
from studio_app.routes import system as system_routes

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_LOCAL_STATE_DIR = Path.home() / "AppData" / "Roaming" / "StudioApp"


def build_app(
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    local_state_dir: Path,
) -> FastAPI:
    app = FastAPI(title="Studio App")
    app.state.conn = conn
    app.state.data_root = data_root
    app.state.local_state_dir = local_state_dir
    app.include_router(system_routes.router)
    app.include_router(books_routes.router)
    app.include_router(settings_routes.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        row = conn.execute("SELECT value FROM app_setting WHERE key='data_root'").fetchone()
        if row and row["value"]:
            return RedirectResponse(url="/library")
        return RedirectResponse(url="/setup")

    @app.get("/setup", include_in_schema=False)
    def setup_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "setup.html")

    @app.get("/library", include_in_schema=False)
    def library_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "library.html")

    @app.get("/books/{book_id}", include_in_schema=False)
    def book_page(book_id: int) -> FileResponse:
        return FileResponse(STATIC_DIR / "book.html")

    return app


def _resolve_local_state_dir() -> Path:
    return Path(DEFAULT_LOCAL_STATE_DIR)


def main() -> int:
    local_state_dir = _resolve_local_state_dir()
    local_state_dir.mkdir(parents=True, exist_ok=True)
    db_path = local_state_dir / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key='data_root'"
    ).fetchone()
    data_root = Path(row["value"]) if row and row["value"] else local_state_dir / "tmp_data_root"
    data_root.mkdir(parents=True, exist_ok=True)
    app = build_app(conn=conn, data_root=data_root, local_state_dir=local_state_dir)
    url = "http://127.0.0.1:8765"
    print(f"Studio App running at {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
