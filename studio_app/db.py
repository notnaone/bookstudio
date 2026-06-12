from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with the project-wide pragmas applied."""
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def migrate(db_path: Path) -> None:
    """Apply migrations idempotently. Phase 1: only 001_initial."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM app_setting WHERE key='schema_version'"
        ).fetchone()
        current = int(row["value"]) if row else 0
    except sqlite3.OperationalError:
        current = 0
    if current < 1:
        sql = (MIGRATIONS_DIR / "001_initial.sql").read_text(encoding="utf-8")
        conn.execute("BEGIN")
        try:
            conn.executescript(sql)
            try:
                conn.execute("COMMIT")
            except sqlite3.OperationalError:
                # executescript() implicitly committed; this is expected
                pass
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                # Transaction already ended
                pass
            raise
    conn.close()
