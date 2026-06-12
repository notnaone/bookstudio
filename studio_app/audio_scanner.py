from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}


def _read_duration(path: Path) -> float:
    """Return file duration in seconds. Returns 0.0 on parse failure."""
    try:
        from mutagen import File as MutagenFile
        m = MutagenFile(str(path))
        if m is None or m.info is None:
            return 0.0
        return float(m.info.length)
    except Exception as exc:
        logger.warning("mutagen failed to read %s: %s", path, exc)
        return 0.0


def _audio_file_count(conn: sqlite3.Connection, book_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM audio_file WHERE book_id = ?", (book_id,)
    ).fetchone()
    return int(row["c"])


def scan_book(conn: sqlite3.Connection, book_id: int) -> int:
    """Scan one book's audio_folder. Returns count of files now in DB.

    Idempotent. Adds new files, refreshes durations for changed ones,
    removes rows for files that have disappeared from an accessible folder.
    """
    row = conn.execute(
        "SELECT audio_folder FROM book WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        return 0
    folder = row["audio_folder"]
    if not folder:
        conn.execute("DELETE FROM audio_file WHERE book_id = ?", (book_id,))
        return 0
    folder_path = Path(folder)
    if not folder_path.is_dir():
        logger.warning("audio folder missing for book %s: %s", book_id, folder)
        return _audio_file_count(conn, book_id)

    on_disk: dict[str, Path] = {}
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES:
            on_disk[str(p.resolve())] = p

    existing = {
        r["path"]: r
        for r in conn.execute(
            "SELECT * FROM audio_file WHERE book_id = ?", (book_id,)
        ).fetchall()
    }

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for old_path in set(existing) - set(on_disk):
        conn.execute(
            "DELETE FROM audio_file WHERE book_id = ? AND path = ?",
            (book_id, old_path),
        )

    for path_str, p in on_disk.items():
        stat = p.stat()
        mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
        if path_str in existing:
            old = existing[path_str]
            if (
                old["mtime"] == mtime_iso
                and int(old["size_bytes"]) == stat.st_size
            ):
                continue
            duration = _read_duration(p)
            conn.execute(
                "UPDATE audio_file SET duration_seconds = ?, size_bytes = ?,"
                " mtime = ?, scanned_at = ? WHERE book_id = ? AND path = ?",
                (duration, stat.st_size, mtime_iso, now, book_id, path_str),
            )
        else:
            duration = _read_duration(p)
            conn.execute(
                "INSERT INTO audio_file (book_id, path, filename,"
                " duration_seconds, size_bytes, mtime, scanned_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book_id, path_str, p.name, duration, stat.st_size, mtime_iso, now),
            )

    return _audio_file_count(conn, book_id)


def recompute_stats(conn: sqlite3.Connection) -> None:
    """Rebuild book_stats and narrator_stats from current audio_file rows.

    Safe to call any time; truncates and re-fills both stat tables.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    conn.execute("DELETE FROM book_stats")
    rows = conn.execute(
        """
        SELECT b.id, b.body_chars, b.pages, b.current_page,
               COALESCE(SUM(a.duration_seconds), 0) AS total_seconds
        FROM book b
        LEFT JOIN audio_file a ON a.book_id = b.id
        GROUP BY b.id
        """
    ).fetchall()
    for r in rows:
        total = float(r["total_seconds"]) or 0.0
        hours = total / 3600.0 if total > 0 else 0.0
        chars_per_h = float(r["body_chars"]) / hours if hours > 0 else 0.0
        pages_per_h = float(r["pages"]) / hours if hours > 0 and r["pages"] else 0.0
        progress = (
            float(r["current_page"]) / float(r["pages"])
            if r["pages"]
            else 0.0
        )
        conn.execute(
            "INSERT INTO book_stats (book_id, total_audio_seconds,"
            " chars_per_hour, pages_per_hour, progress_pct, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (r["id"], total, chars_per_h, pages_per_h, progress, now),
        )

    conn.execute("DELETE FROM narrator_stats")
    rows = conn.execute(
        """
        SELECT n.id,
               (SELECT COUNT(*) FROM narrator_book WHERE narrator_id = n.id) AS assigned,
               (SELECT COUNT(*) FROM narrator_book nb JOIN book b ON b.id = nb.book_id
                WHERE nb.narrator_id = n.id AND b.status = 'done') AS done,
               COALESCE(SUM(bs.total_audio_seconds), 0) AS total_seconds,
               COALESCE(SUM(
                   CASE WHEN COALESCE(bs.total_audio_seconds, 0) > 0
                        THEN b.body_chars ELSE 0 END), 0) AS total_chars,
               COALESCE(SUM(
                   CASE WHEN COALESCE(bs.total_audio_seconds, 0) > 0
                        THEN b.pages ELSE 0 END), 0) AS total_pages
        FROM narrator n
        LEFT JOIN narrator_book nb ON nb.narrator_id = n.id
        LEFT JOIN book b ON b.id = nb.book_id
        LEFT JOIN book_stats bs ON bs.book_id = b.id
        GROUP BY n.id
        """
    ).fetchall()
    for r in rows:
        total = float(r["total_seconds"]) or 0.0
        hours = total / 3600.0 if total > 0 else 0.0
        avg_chars = float(r["total_chars"]) / hours if hours > 0 else 0.0
        avg_pages = float(r["total_pages"]) / hours if hours > 0 else 0.0
        conn.execute(
            "INSERT INTO narrator_stats (narrator_id, books_assigned, books_done,"
            " total_audio_seconds, avg_chars_per_hour, avg_pages_per_hour, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (r["id"], int(r["assigned"]), int(r["done"]), total,
             avg_chars, avg_pages, now),
        )


def scan_all(conn: sqlite3.Connection) -> int:
    """Scan every book's audio folder; then recompute stats once."""
    book_ids = [r["id"] for r in conn.execute("SELECT id FROM book").fetchall()]
    for bid in book_ids:
        scan_book(conn, bid)
    recompute_stats(conn)
    return len(book_ids)
