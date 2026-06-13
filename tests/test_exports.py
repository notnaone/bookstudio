from __future__ import annotations

import csv
from io import StringIO

from studio_app.exports import (
    export_audio_files_csv,
    export_books_csv,
    export_sessions_csv,
)


def _parse_csv(lines: list[str]) -> list[list[str]]:
    return list(csv.reader(StringIO("".join(lines))))


def test_export_books_csv_row_count_and_filters(conn):
    pub_id = conn.execute(
        "INSERT INTO publisher (name) VALUES ('Pub A')"
    ).lastrowid
    narr_id = conn.execute(
        "INSERT INTO narrator (name) VALUES ('Narr A')"
    ).lastrowid
    conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, status,"
        " publisher_id, narrator_id, pages, body_chars, created_at)"
        " VALUES ('book-a', 'Book A', 'txt', '/a', '/a', 'in_progress',"
        " ?, ?, 100, 5000, '2026-06-01T10:00:00')",
        (pub_id, narr_id),
    )
    conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, status,"
        " created_at) VALUES ('book-b', 'Book B', 'txt', '/b', '/b', 'planned',"
        " '2026-06-15T10:00:00')"
    )
    book_a_id = conn.execute("SELECT id FROM book WHERE slug='book-a'").fetchone()["id"]
    conn.execute(
        "INSERT INTO book_stats (book_id, total_audio_seconds, progress_pct)"
        " VALUES (?, 7200, 0.25)",
        (book_a_id,),
    )

    all_lines = list(export_books_csv(conn))
    assert len(_parse_csv(all_lines)) == 3  # header + 2 books

    filtered = list(export_books_csv(conn, status="in_progress"))
    rows = _parse_csv(filtered)
    assert len(rows) == 2
    assert rows[1][2] == "Book A"
    assert rows[1][3] == "Pub A"
    assert float(rows[1][8]) == 2.0

    dated = list(
        export_books_csv(
            conn,
            from_date="2026-06-10T00:00:00",
            to_date="2026-06-20T00:00:00",
        )
    )
    assert len(_parse_csv(dated)) == 2  # header + Book B only


def test_export_sessions_csv_includes_reading_and_work(conn):
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('sess-book', 'Sess Book', 'txt', '/x', '/x')"
    ).lastrowid
    conn.execute(
        "INSERT INTO reading_session"
        " (book_id, started_at, start_page, tracked_progress_page, active_seconds)"
        " VALUES (?, '2026-06-10T09:00:00', 1, 1, 120)",
        (book_id,),
    )
    conn.execute(
        "INSERT INTO work_session"
        " (book_id, kind, started_at, start_page)"
        " VALUES (?, 'recording', '2026-06-11T09:00:00', 1)",
        (book_id,),
    )

    all_lines = list(export_sessions_csv(conn))
    rows = _parse_csv(all_lines)
    assert len(rows) == 3
    kinds = {r[1] for r in rows[1:]}
    assert kinds == {"reading", "recording"}

    reading_only = list(export_sessions_csv(conn, kind="reading"))
    assert len(_parse_csv(reading_only)) == 2


def test_export_audio_files_csv_filter_by_book(conn):
    b1 = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('a1', 'A1', 'txt', '/a', '/a')"
    ).lastrowid
    b2 = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('a2', 'A2', 'txt', '/b', '/b')"
    ).lastrowid
    conn.execute(
        "INSERT INTO audio_file (book_id, path, filename, duration_seconds, size_bytes)"
        " VALUES (?, '/x/a.mp3', 'a.mp3', 60, 1000)",
        (b1,),
    )
    conn.execute(
        "INSERT INTO audio_file (book_id, path, filename, duration_seconds, size_bytes)"
        " VALUES (?, '/x/b.mp3', 'b.mp3', 90, 2000)",
        (b2,),
    )

    lines = list(export_audio_files_csv(conn, book_id=b1))
    rows = _parse_csv(lines)
    assert len(rows) == 2
    assert rows[1][3] == "a.mp3"
