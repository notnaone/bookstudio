from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from studio_app.db_lock import hold
from studio_app.settings import load, save_key

router = APIRouter()

_PACE_UNITS = frozenset({
    "chars_per_hour",
    "pages_per_hour",
    "words_per_hour",
    "sec_per_100_pages",
})
_POSITIVE_INT_KEYS = frozenset({
    "snapshot_interval_seconds",
    "audio_scan_interval_seconds",
    "calendar_poll_interval_seconds",
    "reaper_interval_seconds",
    "session_idle_timeout_seconds",
})


def _validate_setting_value(key: str, value: str) -> str:
    if key == "pace_unit":
        if value not in _PACE_UNITS:
            raise HTTPException(
                status_code=400,
                detail=f"pace_unit must be one of: {', '.join(sorted(_PACE_UNITS))}",
            )
        return value
    if key in _POSITIVE_INT_KEYS:
        try:
            n = int(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{key} must be a positive integer",
            ) from exc
        if n < 1:
            raise HTTPException(
                status_code=400,
                detail=f"{key} must be >= 1",
            )
        return str(n)
    return value


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
    updates: list[tuple[str, str]] = []
    for k, v in payload.items():
        if k not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown setting: {k}")
        updates.append((k, _validate_setting_value(k, str(v))))
    with hold(request.app.state.db_lock):
        for k, v in updates:
            save_key(conn, k, v)
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
    with hold(request.app.state.db_lock):
        save_key(conn, "data_root", str(new_root))
    request.app.state.data_root = new_root
    from studio_app.recovery import persist_data_root

    persist_data_root(request.app.state.local_state_dir, new_root)
    return asdict(load(conn))
