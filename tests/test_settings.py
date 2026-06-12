from __future__ import annotations

from pathlib import Path

from studio_app.db import connect, migrate
from studio_app.settings import (
    REQUIRED_KEYS,
    AppSettings,
    is_configured,
    load,
    save_key,
)


def make_conn(tmp_path: Path):
    db = tmp_path / "studio.live.sqlite"
    migrate(db)
    return connect(db)


def test_load_returns_empty_when_no_settings(tmp_path: Path):
    conn = make_conn(tmp_path)
    s = load(conn)
    assert s.data_root is None
    assert s.pace_unit == "chars_per_hour"


def test_save_and_load_data_root(tmp_path: Path):
    conn = make_conn(tmp_path)
    save_key(conn, "data_root", str(tmp_path / "root"))
    s = load(conn)
    assert s.data_root == str(tmp_path / "root")


def test_is_configured_requires_data_root(tmp_path: Path):
    conn = make_conn(tmp_path)
    assert not is_configured(conn)
    save_key(conn, "data_root", str(tmp_path / "root"))
    assert is_configured(conn)


def test_required_keys_present():
    assert "data_root" in REQUIRED_KEYS


def test_save_key_overwrites(tmp_path: Path):
    conn = make_conn(tmp_path)
    save_key(conn, "pace_unit", "pages_per_hour")
    save_key(conn, "pace_unit", "chars_per_hour")
    s = load(conn)
    assert s.pace_unit == "chars_per_hour"


def test_appsettings_default_intervals():
    s = AppSettings()
    assert s.snapshot_interval_seconds == 300
    assert s.audio_scan_interval_seconds == 300
    assert s.calendar_poll_interval_seconds == 300
    assert s.reaper_interval_seconds == 60
    assert s.session_idle_timeout_seconds == 300
