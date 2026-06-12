from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/heartbeat")
def heartbeat(request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM reading_session WHERE ended_at IS NULL"
    ).fetchone()
    scanner = getattr(request.app.state, "scanner", None)
    reaper = getattr(request.app.state, "reaper", None)
    calendar_poller = getattr(request.app.state, "calendar_poller", None)
    return {
        "active_sessions": int(row["c"]),
        "last_snapshot_at": None,
        "last_calendar_sync_at": (
            calendar_poller.last_sync_at if calendar_poller else None
        ),
        "last_audio_scan_at": scanner.last_scan_at if scanner else None,
        "last_reaper_run_at": reaper.last_run_at if reaper else None,
    }
