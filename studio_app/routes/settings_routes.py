from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from studio_app.settings import load, save_key

router = APIRouter()


@router.get("/api/settings")
def get_settings(request: Request) -> dict:
    conn = request.app.state.conn
    return asdict(load(conn))


@router.patch("/api/settings")
async def patch_settings(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    allowed = {
        "data_root", "local_state_dir",
        "ics_url_studio_1", "ics_url_studio_2", "pace_unit",
        "snapshot_interval_seconds", "audio_scan_interval_seconds",
        "calendar_poll_interval_seconds", "reaper_interval_seconds",
        "session_idle_timeout_seconds",
    }
    for k, v in payload.items():
        if k not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown setting: {k}")
        save_key(conn, k, str(v))
    return asdict(load(conn))


@router.post("/api/setup")
async def setup(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    raw = (payload.get("data_root") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="data_root must be non-empty")
    new_root = Path(raw)
    new_root.mkdir(parents=True, exist_ok=True)
    (new_root / "books").mkdir(exist_ok=True)
    (new_root / "exports").mkdir(exist_ok=True)
    save_key(conn, "data_root", str(new_root))
    request.app.state.data_root = new_root
    from studio_app.recovery import persist_data_root

    persist_data_root(request.app.state.local_state_dir, new_root)
    return asdict(load(conn))
