from __future__ import annotations

import sqlite3
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from studio_app.db import connect, migrate
from studio_app.db_lock import hold
from studio_app.routes import books as books_routes
from studio_app import viewer_routes
from studio_app.routes import marks as marks_routes
from studio_app.routes import narrators as narrators_routes
from studio_app.routes import sessions as sessions_routes
from studio_app.routes import publishers as publishers_routes
from studio_app.routes import schedule as schedule_routes
from studio_app.routes import settings_routes
from studio_app.routes import system as system_routes
from studio_app.calendar_poller import CalendarPoller, poll_calendars
from studio_app.ics_client import fetch_ics
from studio_app.settings import load as load_settings

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_LOCAL_STATE_DIR = Path.home() / "AppData" / "Roaming" / "StudioApp"


@asynccontextmanager
async def _lifespan(app: FastAPI):
    scanner = getattr(app.state, "scanner", None)
    reaper = getattr(app.state, "reaper", None)
    calendar_poller = getattr(app.state, "calendar_poller", None)
    if scanner is not None:
        scanner.start()
    if reaper is not None:
        reaper.start()
    if calendar_poller is not None:
        calendar_poller.start()
    yield
    if calendar_poller is not None:
        calendar_poller.stop()
    if reaper is not None:
        reaper.stop()
    if scanner is not None:
        scanner.stop()


def build_app(
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    local_state_dir: Path,
    scanner=None,
    reaper=None,
    calendar_poller=None,
    db_lock: threading.Lock | None = None,
) -> FastAPI:
    app = FastAPI(title="Studio App", lifespan=_lifespan)
    app.state.conn = conn
    app.state.data_root = data_root
    app.state.local_state_dir = local_state_dir
    app.state.db_lock = db_lock if db_lock is not None else threading.Lock()
    app.include_router(system_routes.router)
    app.include_router(books_routes.router)
    app.include_router(marks_routes.router)
    app.include_router(sessions_routes.router)
    app.include_router(viewer_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(publishers_routes.router)
    app.include_router(narrators_routes.router)
    app.include_router(schedule_routes.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def root(request: Request) -> RedirectResponse:
        row = request.app.state.conn.execute(
            "SELECT value FROM app_setting WHERE key='data_root'"
        ).fetchone()
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

    @app.get("/narrators/{nid}", include_in_schema=False)
    def narrator_page(nid: int) -> FileResponse:
        return FileResponse(STATIC_DIR / "narrator.html")

    @app.get("/live/{book_id}", include_in_schema=False)
    def live_single(book_id: int) -> FileResponse:
        return FileResponse(STATIC_DIR / "live.html")

    @app.get("/live/{a}/{b}", include_in_schema=False)
    def live_split(a: int, b: int) -> FileResponse:
        return FileResponse(STATIC_DIR / "live.html")

    @app.get("/schedule", include_in_schema=False)
    def schedule_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "schedule.html")

    @app.get("/settings", include_in_schema=False)
    def settings_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "settings.html")

    app.state.scanner = scanner
    app.state.reaper = reaper
    app.state.calendar_poller = calendar_poller
    return app


def _calendar_urls_provider(conn: sqlite3.Connection) -> dict[str, str | None]:
    settings = load_settings(conn)
    return {
        "studio_1": settings.ics_url_studio_1,
        "studio_2": settings.ics_url_studio_2,
    }


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

    from studio_app.audio_scanner import scan_all
    from studio_app.background import AudioScanner
    from studio_app.reaper import SessionReaper, reap_stale_sessions

    db_lock = threading.Lock()
    settings = load_settings(conn)

    def locked_scan_all(c: sqlite3.Connection) -> int:
        with hold(db_lock):
            return scan_all(c)

    def locked_reap(c: sqlite3.Connection) -> None:
        with hold(db_lock):
            reap_stale_sessions(c, settings.session_idle_timeout_seconds)

    scanner = AudioScanner(
        conn,
        interval_seconds=settings.audio_scan_interval_seconds,
        scan_fn=locked_scan_all,
    )
    reaper = SessionReaper(
        conn,
        idle_timeout_seconds=settings.session_idle_timeout_seconds,
        interval_seconds=settings.reaper_interval_seconds,
        reap_fn=locked_reap,
    )

    def locked_poll_once() -> None:
        with hold(db_lock):
            poll_calendars(
                conn,
                fetch_fn=fetch_ics,
                urls=_calendar_urls_provider(conn),
            )

    calendar_poller = CalendarPoller(
        conn,
        interval_seconds=settings.calendar_poll_interval_seconds,
        fetch_fn=fetch_ics,
        urls_provider=_calendar_urls_provider,
        poll_fn=locked_poll_once,
    )
    app = build_app(
        conn=conn,
        data_root=data_root,
        local_state_dir=local_state_dir,
        scanner=scanner,
        reaper=reaper,
        calendar_poller=calendar_poller,
        db_lock=db_lock,
    )
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
