from __future__ import annotations

import json

from studio_app.marks_restore import restore_marks_from_disk


def test_restore_marks_from_disk_inserts_rows(conn, data_root):
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('restore-me', 'Restore Me', 'txt', '/x', '/x')"
    ).lastrowid
    book_dir = data_root / "books" / "restore-me"
    book_dir.mkdir(parents=True)
    marks = [
        {
            "id": 99,
            "book_id": book_id,
            "page": 2,
            "x_pct": 10.0,
            "y_pct": 20.0,
            "w_pct": 30.0,
            "h_pct": 15.0,
            "color": "#FF0000",
            "comment": "note",
            "created_at": "2026-06-01",
        }
    ]
    (book_dir / "marks.json").write_text(json.dumps(marks), encoding="utf-8")

    result = restore_marks_from_disk(conn, data_root)
    assert result["restored"] == 1
    assert result["skipped_existing"] == 0
    assert result["errors"] == []

    row = conn.execute("SELECT * FROM mark WHERE book_id = ?", (book_id,)).fetchone()
    assert row is not None
    assert row["page"] == 2
    assert row["comment"] == "note"


def test_restore_marks_skips_existing(conn, data_root):
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('skip-me', 'Skip Me', 'txt', '/x', '/x')"
    ).lastrowid
    conn.execute(
        "INSERT INTO mark (book_id, page, x_pct, y_pct, w_pct, h_pct)"
        " VALUES (?, 1, 5, 5, 10, 10)",
        (book_id,),
    )
    book_dir = data_root / "books" / "skip-me"
    book_dir.mkdir(parents=True)
    marks = [{"page": 1, "x_pct": 5, "y_pct": 5, "w_pct": 10, "h_pct": 10}]
    (book_dir / "marks.json").write_text(json.dumps(marks), encoding="utf-8")

    result = restore_marks_from_disk(conn, data_root)
    assert result["restored"] == 0
    assert result["skipped_existing"] == 1


async def test_marks_restore_endpoint(client, conn, data_root):
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path)"
        " VALUES ('api-restore', 'API Restore', 'txt', '/x', '/x')"
    ).lastrowid
    book_dir = data_root / "books" / "api-restore"
    book_dir.mkdir(parents=True)
    marks = [{"page": 3, "x_pct": 1, "y_pct": 2, "w_pct": 3, "h_pct": 4}]
    (book_dir / "marks.json").write_text(json.dumps(marks), encoding="utf-8")

    r = await client.post("/api/marks/restore")
    assert r.status_code == 200
    body = r.json()
    assert body["restored"] == 1
    count = conn.execute(
        "SELECT COUNT(*) AS c FROM mark WHERE book_id = ?", (book_id,)
    ).fetchone()["c"]
    assert count == 1
