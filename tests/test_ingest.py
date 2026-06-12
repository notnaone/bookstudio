from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from studio_app.ingest import ingest_book

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_book_copies_source_under_data_root(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "incoming.txt"
    shutil.copy(FIXTURES / "sample.txt", src)
    book_id = ingest_book(conn, data_root, src, title="Sample Book")
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    assert row["slug"] == "sample-book"
    expected_src = data_root / "books" / "sample-book" / "source" / "incoming.txt"
    assert expected_src.exists()
    assert row["source_path"] == str(expected_src)
    assert row["format"] == "txt"
    assert row["body_chars"] > 0


def test_ingest_book_creates_metadata_json(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "incoming.txt"
    shutil.copy(FIXTURES / "sample.txt", src)
    ingest_book(conn, data_root, src, title="Sample Book")
    meta = data_root / "books" / "sample-book" / "metadata.json"
    assert meta.exists()
    text = meta.read_text(encoding="utf-8")
    assert "body_chars" in text


def test_ingest_book_dedupes_slug_on_collision(conn, data_root: Path, tmp_path: Path):
    src1 = tmp_path / "a.txt"
    src2 = tmp_path / "b.txt"
    shutil.copy(FIXTURES / "sample.txt", src1)
    shutil.copy(FIXTURES / "sample.txt", src2)
    id1 = ingest_book(conn, data_root, src1, title="Same Title")
    id2 = ingest_book(conn, data_root, src2, title="Same Title")
    slugs = [
        conn.execute("SELECT slug FROM book WHERE id=?", (i,)).fetchone()["slug"]
        for i in (id1, id2)
    ]
    assert slugs[0] != slugs[1]
    assert slugs[0] == "same-title"
    assert slugs[1] == "same-title-2"


def test_ingest_book_raises_on_unsupported_format(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "thing.xyz"
    src.write_text("nope")
    with pytest.raises(ValueError):
        ingest_book(conn, data_root, src, title="Bad")
    # Cleanup happened (no orphan directory left behind):
    assert not (data_root / "books" / "bad").exists()


def test_ingest_book_initial_status_planned(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "x.txt"
    shutil.copy(FIXTURES / "sample.txt", src)
    book_id = ingest_book(conn, data_root, src, title="Status Check")
    row = conn.execute("SELECT status, current_page FROM book WHERE id=?", (book_id,)).fetchone()
    assert row["status"] == "planned"
    assert row["current_page"] == 1
