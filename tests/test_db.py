from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from studio_app.db import connect, migrate


def test_migrate_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    expected = {
        "publisher", "narrator", "book", "narrator_book",
        "schedule_item", "reading_session", "work_session",
        "audio_file", "mark", "book_stats", "narrator_stats",
        "app_setting",
    }
    assert expected.issubset(names)


def test_migrate_records_schema_version(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key='schema_version'"
    ).fetchone()
    assert row["value"] == "1"


def test_migrate_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    migrate(db_path)
    conn = connect(db_path)
    rows = conn.execute("SELECT COUNT(*) AS c FROM app_setting").fetchone()
    assert rows["c"] >= 1


def test_connect_uses_wal_mode(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()
    assert mode[0].lower() == "wal"


def test_connect_enforces_foreign_keys(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    fk = conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk[0] == 1


def test_book_check_constraint_rejects_bad_status(tmp_path: Path):
    db_path = tmp_path / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO book (slug, title, source_path, view_path, format, status)"
            " VALUES ('x', 't', '/a', '/b', 'pdf', 'WUT')"
        )
