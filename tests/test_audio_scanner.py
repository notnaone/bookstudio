from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from studio_app.audio_scanner import scan_book, recompute_stats
from studio_app.ingest import ingest_book

FIXTURES = Path(__file__).parent / "fixtures"


def _insert_book_with_folder(conn, data_root: Path, audio_folder: Path):
    src = audio_folder.parent / "src.txt"
    src.write_text("Chapter 1\nHello world.")
    bid = ingest_book(
        conn, data_root, src, title="Audio Book",
        audio_folder=str(audio_folder),
    )
    return bid


def test_scan_book_no_folder_set_returns_zero(conn, data_root, tmp_path):
    # Book with no audio_folder — scanner should return 0 cleanly.
    src = tmp_path / "x.txt"
    src.write_text("hi")
    bid = ingest_book(conn, data_root, src, title="No Folder")
    n = scan_book(conn, bid)
    assert n == 0
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 0


def test_scan_book_finds_mp3(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "chapter01.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    n = scan_book(conn, bid)
    assert n == 1
    row = conn.execute("SELECT * FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert row["filename"] == "chapter01.mp3"
    assert row["duration_seconds"] > 0


def test_scan_book_idempotent(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    scan_book(conn, bid)
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 1


def test_scan_book_picks_up_new_files_on_rescan(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch1.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    shutil.copy(FIXTURES / "silence.mp3", af / "ch2.mp3")
    scan_book(conn, bid)
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 2


def test_scan_book_drops_rows_for_deleted_files(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    p = af / "ch.mp3"
    shutil.copy(FIXTURES / "silence.mp3", p)
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    p.unlink()
    scan_book(conn, bid)
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 0


def test_scan_book_ignores_non_audio(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    (af / "notes.txt").write_text("nope")
    shutil.copy(FIXTURES / "silence.mp3", af / "real.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    rows = conn.execute("SELECT filename FROM audio_file WHERE book_id=?", (bid,)).fetchall()
    names = sorted(r["filename"] for r in rows)
    assert names == ["real.mp3"]


def test_scan_book_handles_missing_folder(conn, data_root, tmp_path):
    bid = _insert_book_with_folder(conn, data_root, tmp_path / "nonexistent")
    # Folder doesn't exist on disk — scanner should not crash.
    n = scan_book(conn, bid)
    assert n == 0


def test_scan_book_preserves_rows_when_folder_missing(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    shutil.rmtree(af)
    n = scan_book(conn, bid)
    assert n == 1
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 1


def test_scan_book_clears_rows_when_folder_cleared(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    conn.execute("UPDATE book SET audio_folder = NULL WHERE id = ?", (bid,))
    n = scan_book(conn, bid)
    assert n == 0
    rows = conn.execute("SELECT COUNT(*) AS c FROM audio_file WHERE book_id=?", (bid,)).fetchone()
    assert rows["c"] == 0


def test_recompute_book_stats_zero_when_no_audio(conn, data_root, tmp_path):
    src = tmp_path / "x.txt"
    src.write_text("hi")
    bid = ingest_book(conn, data_root, src, title="Zero Audio")
    recompute_stats(conn)
    row = conn.execute("SELECT * FROM book_stats WHERE book_id=?", (bid,)).fetchone()
    assert row is not None
    assert row["total_audio_seconds"] == 0
    assert row["chars_per_hour"] == 0


def test_recompute_book_stats_computes_chars_per_hour(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "a.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    scan_book(conn, bid)
    recompute_stats(conn)
    row = conn.execute("SELECT * FROM book_stats WHERE book_id=?", (bid,)).fetchone()
    assert row["total_audio_seconds"] > 0
    assert row["chars_per_hour"] > 0


def test_recompute_narrator_stats_credits_past_assignment(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "x.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES (?, ?), (?, ?)",
        ("Past", None, "Current", None),
    )
    n1 = conn.execute("SELECT id FROM narrator WHERE name='Past'").fetchone()["id"]
    n2 = conn.execute("SELECT id FROM narrator WHERE name='Current'").fetchone()["id"]
    conn.execute("UPDATE book SET narrator_id = ? WHERE id = ?", (n1, bid))
    conn.execute(
        "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)",
        (n1, bid),
    )
    scan_book(conn, bid)
    conn.execute("UPDATE book SET narrator_id = ? WHERE id = ?", (n2, bid))
    conn.execute(
        "UPDATE narrator_book SET finished_at = CURRENT_TIMESTAMP"
        " WHERE narrator_id = ? AND book_id = ?",
        (n1, bid),
    )
    conn.execute(
        "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)",
        (n2, bid),
    )
    recompute_stats(conn)
    past = conn.execute(
        "SELECT * FROM narrator_stats WHERE narrator_id=?", (n1,)
    ).fetchone()
    assert past is not None
    assert past["total_audio_seconds"] > 0


def test_recompute_narrator_stats_excludes_books_without_audio(conn, data_root, tmp_path):
    src = tmp_path / "plain.txt"
    src.write_text("no audio here")
    quiet_id = ingest_book(conn, data_root, src, title="Quiet")
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "x.mp3")
    loud_id = _insert_book_with_folder(conn, data_root, af)
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES (?, ?)",
        ("Mix", None),
    )
    nid = conn.execute("SELECT id FROM narrator WHERE name='Mix'").fetchone()["id"]
    for bid in (quiet_id, loud_id):
        conn.execute("UPDATE book SET narrator_id = ? WHERE id = ?", (nid, bid))
        conn.execute(
            "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)",
            (nid, bid),
        )
    scan_book(conn, loud_id)
    recompute_stats(conn)
    row = conn.execute("SELECT * FROM narrator_stats WHERE narrator_id=?", (nid,)).fetchone()
    book = conn.execute("SELECT body_chars FROM book WHERE id=?", (loud_id,)).fetchone()
    assert row["total_audio_seconds"] > 0
    assert row["avg_chars_per_hour"] == pytest.approx(
        float(book["body_chars"]) / (row["total_audio_seconds"] / 3600.0),
        rel=0.01,
    )


def test_recompute_narrator_stats(conn, data_root, tmp_path):
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "x.mp3")
    bid = _insert_book_with_folder(conn, data_root, af)
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES (?, ?)",
        ("Reader", None),
    )
    nid = conn.execute("SELECT id FROM narrator WHERE name='Reader'").fetchone()["id"]
    conn.execute("UPDATE book SET narrator_id = ? WHERE id = ?", (nid, bid))
    conn.execute(
        "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)",
        (nid, bid),
    )
    scan_book(conn, bid)
    recompute_stats(conn)
    row = conn.execute("SELECT * FROM narrator_stats WHERE narrator_id=?", (nid,)).fetchone()
    assert row is not None
    assert row["books_assigned"] == 1
    assert row["total_audio_seconds"] > 0
    assert row["avg_chars_per_hour"] > 0
