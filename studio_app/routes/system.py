from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

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
    snapshot_job = getattr(request.app.state, "snapshot_job", None)
    return {
        "active_sessions": int(row["c"]),
        "last_snapshot_at": (
            snapshot_job.last_snapshot_at if snapshot_job else None
        ),
        "last_calendar_sync_at": (
            calendar_poller.last_sync_at if calendar_poller else None
        ),
        "last_audio_scan_at": scanner.last_scan_at if scanner else None,
        "last_reaper_run_at": reaper.last_run_at if reaper else None,
    }


@router.post("/api/snapshot")
def trigger_snapshot(request: Request) -> dict:
    snapshot_job = getattr(request.app.state, "snapshot_job", None)
    if snapshot_job is None:
        raise HTTPException(503, "Snapshot job not configured")
    nbytes = snapshot_job.run_once()
    return {
        "ok": True,
        "bytes": nbytes,
        "snapshot_at": snapshot_job.last_snapshot_at,
    }
