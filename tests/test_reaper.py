from __future__ import annotations

from studio_app.reaper import SessionReaper, reap_stale_sessions


def _insert_open_session(conn, *, last_heartbeat_at: str) -> int:
    conn.execute(
        "INSERT INTO book (slug, title, source_path, view_path, format, current_page)"
        " VALUES ('reap-test', 'Reap Test', '/src', '/view', 'pdf', 5)"
    )
    book_id = conn.execute("SELECT id FROM book WHERE slug = 'reap-test'").fetchone()["id"]
    cur = conn.execute(
        """
        INSERT INTO reading_session
          (book_id, started_at, start_page, tracked_progress_page,
           last_heartbeat_at, ended_at, auto_closed)
        VALUES (?, '2026-06-01T10:00:00+00:00', 5, 12, ?, NULL, 0)
        """,
        (book_id, last_heartbeat_at),
    )
    return int(cur.lastrowid)


def test_reap_closes_stale_session(conn):
    session_id = _insert_open_session(
        conn, last_heartbeat_at="2026-06-01T09:50:00+00:00"
    )

    reap_stale_sessions(conn, idle_timeout_seconds=300)

    row = conn.execute(
        "SELECT ended_at, end_page, auto_closed FROM reading_session WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["ended_at"] is not None
    assert row["end_page"] == 12
    assert row["auto_closed"] == 1


def test_session_reaper_runs_reap_fn(conn):
    session_id = _insert_open_session(
        conn, last_heartbeat_at="2026-06-01T09:50:00+00:00"
    )
    reaper = SessionReaper(
        conn,
        idle_timeout_seconds=300,
        interval_seconds=60,
        reap_fn=lambda c: reap_stale_sessions(c, 300),
    )
    reaper._reap_fn(conn)
    reaper.last_run_at = "2026-06-01T10:00:00+00:00"

    row = conn.execute(
        "SELECT ended_at, auto_closed FROM reading_session WHERE id = ?",
        (session_id,),
    ).fetchone()
    assert row["ended_at"] is not None
    assert row["auto_closed"] == 1
