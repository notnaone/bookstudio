from __future__ import annotations

import time
from pathlib import Path

import pytest


async def test_export_books_csv_streams(client, conn):
    conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('csv-book', 'CSV Book', 'txt', '/x', '/x')"
    )
    r = await client.get("/api/export/books.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "CSV Book" in r.text


async def test_export_books_save_writes_file(client, conn, data_root: Path):
    conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('save-book', 'Save Book', 'txt', '/x', '/x')"
    )
    exports_dir = data_root / "exports"
    exports_dir.mkdir(exist_ok=True)
    before = list(exports_dir.glob("books-*.csv"))
    r = await client.get("/api/export/books.csv", params={"save": 1})
    assert r.status_code == 200
    after = list(exports_dir.glob("books-*.csv"))
    assert len(after) == len(before) + 1
    assert "Save Book" in after[-1].read_text(encoding="utf-8")


async def test_export_cleanup_deletes_old_files(client, data_root: Path):
    exports_dir = data_root / "exports"
    exports_dir.mkdir(exist_ok=True)
    old = exports_dir / "books-old.csv"
    old.write_text("id\n", encoding="utf-8")
    old_time = time.time() - 10 * 86400
    import os

    os.utime(old, (old_time, old_time))

    r = await client.post("/api/export/cleanup", json={"older_than_days": 7})
    assert r.status_code == 200
    assert r.json()["deleted"] == 1
    assert not old.exists()


async def test_export_cleanup_rejects_invalid_body(client):
    r = await client.post("/api/export/cleanup", json={"older_than_days": -1})
    assert r.status_code == 400


async def test_export_sessions_kind_filter(client, conn):
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('k-book', 'K Book', 'txt', '/x', '/x')"
    ).lastrowid
    conn.execute(
        "INSERT INTO reading_session (book_id, started_at, start_page, tracked_progress_page)"
        " VALUES (?, '2026-06-01T09:00:00', 1, 1)",
        (book_id,),
    )
    r = await client.get("/api/export/sessions.csv", params={"kind": "reading"})
    assert r.status_code == 200
    assert "reading" in r.text

    r = await client.get("/api/export/sessions.csv", params={"kind": "nope"})
    assert r.status_code == 400
