from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/heartbeat")
def heartbeat(request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM reading_session WHERE ended_at IS NULL"
    ).fetchone()
    return {
        "active_sessions": int(row["c"]),
        "last_snapshot_at": None,
        "last_calendar_sync_at": None,
    }
