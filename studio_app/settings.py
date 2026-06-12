from __future__ import annotations

import sqlite3
from dataclasses import dataclass

REQUIRED_KEYS = ("data_root",)

_DEFAULTS = {
    "pace_unit": "chars_per_hour",
    "snapshot_interval_seconds": "300",
    "audio_scan_interval_seconds": "300",
    "calendar_poll_interval_seconds": "300",
    "reaper_interval_seconds": "60",
    "session_idle_timeout_seconds": "300",
}


@dataclass
class AppSettings:
    data_root: str | None = None
    local_state_dir: str | None = None
    ics_url_studio_1: str | None = None
    ics_url_studio_2: str | None = None
    pace_unit: str = "chars_per_hour"
    snapshot_interval_seconds: int = 300
    audio_scan_interval_seconds: int = 300
    calendar_poll_interval_seconds: int = 300
    reaper_interval_seconds: int = 60
    session_idle_timeout_seconds: int = 300


def load(conn: sqlite3.Connection) -> AppSettings:
    rows = conn.execute("SELECT key, value FROM app_setting").fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    merged = {**_DEFAULTS, **raw}
    return AppSettings(
        data_root=merged.get("data_root"),
        local_state_dir=merged.get("local_state_dir"),
        ics_url_studio_1=merged.get("ics_url_studio_1"),
        ics_url_studio_2=merged.get("ics_url_studio_2"),
        pace_unit=merged.get("pace_unit", "chars_per_hour"),
        snapshot_interval_seconds=int(merged.get("snapshot_interval_seconds", 300)),
        audio_scan_interval_seconds=int(merged.get("audio_scan_interval_seconds", 300)),
        calendar_poll_interval_seconds=int(merged.get("calendar_poll_interval_seconds", 300)),
        reaper_interval_seconds=int(merged.get("reaper_interval_seconds", 60)),
        session_idle_timeout_seconds=int(merged.get("session_idle_timeout_seconds", 300)),
    )


def save_key(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def is_configured(conn: sqlite3.Connection) -> bool:
    s = load(conn)
    return s.data_root is not None and s.data_root != ""
