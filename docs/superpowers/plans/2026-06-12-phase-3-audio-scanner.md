# Phase 3 — Audio Scanner & Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover audio files inside each book's `audio_folder`, persist their durations, recompute `book_stats` and `narrator_stats`, and surface those numbers in the existing UI. Introduces the app's first background thread (`AudioScanner`) plus a manual "Re-scan now" trigger. By the end, the book and narrator screens show real hours-recorded, chars/hour, and pages/hour.

**Architecture:** Scan logic is a synchronous Python module (`studio_app/audio_scanner.py`) that walks a folder, reads file durations via `mutagen`, upserts `audio_file` rows, then recomputes `book_stats` and `narrator_stats`. The background loop is a single daemon thread started in `main.py`. UI gets a `POST /api/books/:id/rescan_audio` button and the JSON book/narrator responses include their stats rows.

**Tech Stack:** Unchanged + `mutagen` (already declared in `pyproject.toml` since Phase 1 — book_analyzer pulls it in).

**Prereqs:** Phase 2 merged + hardening commit `6a368c5` on `master`. Baseline: 78 passed + 2 skipped.

---

## File structure

**New files:**
```
studio_app/audio_scanner.py       # scan(book_id, conn) + scan_all(conn) + recompute_stats(conn)
studio_app/background.py          # AudioScanner thread class, start()/stop()
tests/test_audio_scanner.py
tests/test_routes_audio.py
tests/fixtures/silence.mp3        # generated tiny MP3 fixture (see Task 0)
```

**Modified files:**
```
studio_app/main.py                # start scanner thread in main(); expose helpers
studio_app/routes/books.py        # POST /api/books/:id/rescan_audio + book_stats in GET
studio_app/routes/narrators.py    # narrator_stats embedded in GET
studio_app/routes/system.py       # heartbeat reports last_audio_scan_at
studio_app/static/book.html       # h_recorded, chars_per_hour, pages_per_hour cells + Re-scan button
studio_app/static/narrator.html   # narrator_stats panel
studio_app/static/app.js          # setupBookPage updates stats; new onRescanAudio
```

---

## Cross-cutting rules

- All scan paths are tested with `tmp_path` fixtures — never touch the real filesystem outside it.
- The scanner is idempotent: re-running over the same folder must not duplicate rows.
- All durations are stored as `REAL` seconds (mutagen returns `.info.length` as float).
- `book_stats` and `narrator_stats` are derived; safe to drop and re-recompute.
- Background thread is daemon=True so it dies with the main process.

---

## Task 0: Generate a tiny silent-MP3 fixture and confirm mutagen reads it

**Files:**
- Create: `tests/fixtures/silence.mp3` (generated, committed)
- Create: `tests/fixtures/_generate_silence.py` (a script that produces the fixture — committed for reproducibility)

- [ ] **Step 1: Generator script**

Create `tests/fixtures/_generate_silence.py`:
```python
"""Generate a 2-second silent MP3 fixture. Run once; commit the output."""
from __future__ import annotations
import struct
import sys
from pathlib import Path

# Build the smallest possible MPEG-1 Layer III silent frame.
# This is a 2-second MP3 made of repeated minimal-bitrate silent frames.
# We hand-roll the bytes so we don't need ffmpeg or pydub.
#
# Each MPEG-1 L3 frame at 32 kbps / 22050 Hz / mono is 104 bytes.
# 2 seconds at 22050 Hz ≈ 86 frames.

HEADER = bytes.fromhex("FFFB1000")  # mpeg1 L3, 32 kbps, 22050 Hz, mono, no CRC
PAYLOAD = bytes(100)                 # 100 zero bytes of silence per frame
FRAME = HEADER + PAYLOAD
NUM_FRAMES = 86

out = Path(__file__).parent / "silence.mp3"
out.write_bytes(FRAME * NUM_FRAMES)
print(f"wrote {out} ({out.stat().st_size} bytes, {NUM_FRAMES} frames)")
```

- [ ] **Step 2: Run it**

`uv run python tests/fixtures/_generate_silence.py`. Verify file is created.

- [ ] **Step 3: Validate mutagen reads it**

```bash
uv run python -c "from mutagen.mp3 import MP3; m=MP3('tests/fixtures/silence.mp3'); print('length:', m.info.length)"
```
Expected: a positive float roughly 2.0 (give or take a frame).

If mutagen reports `length=0` or raises HeaderNotFoundError, the fixture is malformed. STOP and report BLOCKED with the actual mutagen output. Do not paper over by faking durations in tests.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/silence.mp3 tests/fixtures/_generate_silence.py
git commit -m "test: tiny silent MP3 fixture for audio scanner"
```

---

## Task 1: `audio_scanner.scan_book` — single-book scan

**Files:**
- Create: `studio_app/audio_scanner.py`
- Test: `tests/test_audio_scanner.py`

- [ ] **Step 1: Failing tests**

Create `tests/test_audio_scanner.py`:
```python
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
```

Run `uv run pytest tests/test_audio_scanner.py -v` → ImportError.

- [ ] **Step 2: Implement**

Create `studio_app/audio_scanner.py`:
```python
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


def scan_book(conn: sqlite3.Connection, book_id: int) -> int:
    """Scan one book's audio_folder. Returns count of files now in DB.

    Idempotent. Adds new files, refreshes durations for changed ones,
    removes rows for files that have disappeared.
    """
    row = conn.execute(
        "SELECT audio_folder FROM book WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        return 0
    folder = row["audio_folder"]
    if not folder:
        return 0
    folder_path = Path(folder)
    if not folder_path.exists() or not folder_path.is_dir():
        return 0

    # Collect every audio file currently on disk.
    on_disk: dict[str, Path] = {}
    for p in folder_path.iterdir():
        if p.is_file() and p.suffix.lower() in AUDIO_SUFFIXES:
            on_disk[str(p.resolve())] = p

    # Existing DB rows.
    existing = {
        r["path"]: r
        for r in conn.execute(
            "SELECT * FROM audio_file WHERE book_id = ?", (book_id,)
        ).fetchall()
    }

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Delete rows whose files have disappeared.
    for old_path in set(existing) - set(on_disk):
        conn.execute("DELETE FROM audio_file WHERE path = ?", (old_path,))

    # Insert or update remaining.
    for path_str, p in on_disk.items():
        stat = p.stat()
        mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
        duration = _read_duration(p)
        if path_str in existing:
            old = existing[path_str]
            if (
                old["mtime"] != mtime_iso
                or float(old["duration_seconds"]) != duration
                or int(old["size_bytes"]) != stat.st_size
            ):
                conn.execute(
                    "UPDATE audio_file SET duration_seconds = ?, size_bytes = ?,"
                    " mtime = ?, scanned_at = ? WHERE path = ?",
                    (duration, stat.st_size, mtime_iso, now, path_str),
                )
        else:
            conn.execute(
                "INSERT INTO audio_file (book_id, path, filename,"
                " duration_seconds, size_bytes, mtime, scanned_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book_id, path_str, p.name, duration, stat.st_size, mtime_iso, now),
            )

    count = conn.execute(
        "SELECT COUNT(*) AS c FROM audio_file WHERE book_id = ?", (book_id,)
    ).fetchone()["c"]
    return int(count)


def recompute_stats(conn: sqlite3.Connection) -> None:
    """Rebuild book_stats and narrator_stats from current audio_file rows.

    Safe to call any time; truncates and re-fills both stat tables.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # --- book_stats ---
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

    # --- narrator_stats ---
    conn.execute("DELETE FROM narrator_stats")
    rows = conn.execute(
        """
        SELECT n.id,
               (SELECT COUNT(*) FROM narrator_book WHERE narrator_id = n.id) AS assigned,
               (SELECT COUNT(*) FROM narrator_book nb JOIN book b ON b.id = nb.book_id
                WHERE nb.narrator_id = n.id AND b.status = 'done') AS done,
               COALESCE(SUM(bs.total_audio_seconds), 0) AS total_seconds,
               COALESCE(SUM(b.body_chars), 0) AS total_chars,
               COALESCE(SUM(b.pages), 0) AS total_pages
        FROM narrator n
        LEFT JOIN book b ON b.narrator_id = n.id
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
```

- [ ] **Step 3: Confirm pass**

`uv run pytest tests/test_audio_scanner.py -v` → 7 passed.
Full suite: `uv run pytest -q` → expect 85 passed + 2 skipped.

- [ ] **Step 4: Commit**

```bash
git add studio_app/audio_scanner.py tests/test_audio_scanner.py
git commit -m "feat(studio): audio scanner — per-book scan + stats recompute"
```

---

## Task 2: `recompute_stats` regression tests

**Files:**
- Modify: `tests/test_audio_scanner.py` (append stats tests)

- [ ] **Step 1: Failing tests**

Append:
```python


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
```

- [ ] **Step 2: Confirm pass**

`uv run pytest tests/test_audio_scanner.py -v` → 10 passed (7 + 3).
Full suite: 88 passed + 2 skipped.

- [ ] **Step 3: Commit**

```bash
git add tests/test_audio_scanner.py
git commit -m "test: book_stats + narrator_stats recompute coverage"
```

---

## Task 3: Background scanner thread

**Files:**
- Create: `studio_app/background.py`
- Test: `tests/test_background.py`

- [ ] **Step 1: Failing tests**

Create `tests/test_background.py`:
```python
from __future__ import annotations

import threading
import time

from studio_app.background import AudioScanner


def test_audio_scanner_runs_once_immediately(conn):
    calls = []
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: calls.append(c))
    scanner.start()
    time.sleep(0.2)
    scanner.stop()
    assert len(calls) >= 1


def test_audio_scanner_stop_is_idempotent(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    scanner.stop()
    scanner.stop()  # must not raise


def test_audio_scanner_thread_is_daemon(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    assert scanner._thread is not None and scanner._thread.daemon
    scanner.stop()


def test_audio_scanner_records_last_scan_at(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    time.sleep(0.2)
    scanner.stop()
    assert scanner.last_scan_at is not None
```

- [ ] **Step 2: Implement**

Create `studio_app/background.py`:
```python
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)


class AudioScanner:
    """Daemon thread that runs `scan_fn(conn)` every `interval_seconds`.

    Single instance per app process. `scan_fn` is injected for testability.
    """

    def __init__(
        self,
        conn,
        interval_seconds: int,
        scan_fn: Callable[..., None],
    ):
        self._conn = conn
        self._interval = interval_seconds
        self._scan_fn = scan_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_scan_at: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AudioScanner")
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan_fn(self._conn)
                self.last_scan_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            except Exception:
                logger.exception("AudioScanner iteration failed; will retry")
            # Sleep in small slices so stop() returns promptly.
            for _ in range(self._interval):
                if self._stop_event.wait(timeout=1.0):
                    return
```

- [ ] **Step 3: Confirm pass**

`uv run pytest tests/test_background.py -v` → 4 passed.
Full suite: 92 passed + 2 skipped.

- [ ] **Step 4: Commit**

```bash
git add studio_app/background.py tests/test_background.py
git commit -m "feat(studio): background AudioScanner daemon thread"
```

---

## Task 4: Wire scanner into main(), expose status

**Files:**
- Modify: `studio_app/main.py` (start scanner)
- Modify: `studio_app/routes/system.py` (heartbeat reports last_audio_scan_at)
- Modify: `tests/conftest.py` (skip starting the thread in tests)

- [ ] **Step 1: Pass scanner via app.state**

Edit `studio_app/main.py`. Inside `build_app`, BEFORE `return app`, add a parameter and store:

Change signature:
```python
def build_app(
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    local_state_dir: Path,
    scanner=None,
) -> FastAPI:
```

In the body, add:
```python
    app.state.scanner = scanner
```

In `main()`, after building the app, create and start the scanner:
```python
    from studio_app.audio_scanner import scan_all
    from studio_app.background import AudioScanner
    settings_row = load_settings_interval(conn)  # see below; just read app_setting
    scanner = AudioScanner(conn, interval_seconds=settings_row, scan_fn=scan_all)
    app.state.scanner = scanner
    scanner.start()
```

Replace `load_settings_interval` with an inline read:
```python
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key='audio_scan_interval_seconds'"
    ).fetchone()
    interval = int(row["value"]) if row else 300
    scanner = AudioScanner(conn, interval_seconds=interval, scan_fn=scan_all)
```

- [ ] **Step 2: Heartbeat exposes scanner status**

Edit `studio_app/routes/system.py`:
```python
@router.get("/api/heartbeat")
def heartbeat(request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM reading_session WHERE ended_at IS NULL"
    ).fetchone()
    scanner = getattr(request.app.state, "scanner", None)
    return {
        "active_sessions": int(row["c"]),
        "last_snapshot_at": None,
        "last_calendar_sync_at": None,
        "last_audio_scan_at": scanner.last_scan_at if scanner else None,
    }
```

- [ ] **Step 3: Test update**

Append to `tests/test_routes_system.py`:
```python


async def test_heartbeat_includes_last_audio_scan_at_key(client):
    r = await client.get("/api/heartbeat")
    body = r.json()
    assert "last_audio_scan_at" in body
```

The `app` fixture doesn't pass a scanner, so this should be `None`. That's fine.

- [ ] **Step 4: Confirm pass**

Full suite: `uv run pytest -q` → expect 93 passed + 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add studio_app/main.py studio_app/routes/system.py tests/test_routes_system.py
git commit -m "feat(studio): wire AudioScanner into main(); heartbeat reports last scan"
```

---

## Task 5: Books API exposes `book_stats` + manual rescan endpoint

**Files:**
- Modify: `studio_app/routes/books.py` (embed stats in GET; add POST /rescan_audio)
- Modify: `tests/test_routes_books.py` (verify stats key present)
- Create: `tests/test_routes_audio.py`

- [ ] **Step 1: Embed stats in get_book**

In `studio_app/routes/books.py`, modify `_book_row_to_dict` to also fetch the stats row. The cleanest approach is a new helper that takes both row + conn:

Add helper near the existing `_book_row_to_dict`:
```python
def _stats_for_book(conn, book_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM book_stats WHERE book_id = ?", (book_id,)
    ).fetchone()
    if row is None:
        return {
            "total_audio_seconds": 0,
            "chars_per_hour": 0,
            "pages_per_hour": 0,
            "progress_pct": 0,
        }
    return {
        "total_audio_seconds": row["total_audio_seconds"],
        "chars_per_hour": row["chars_per_hour"],
        "pages_per_hour": row["pages_per_hour"],
        "progress_pct": row["progress_pct"],
    }
```

In `get_book`, expand the response:
```python
@router.get("/api/books/{book_id}")
def get_book(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    body = _book_row_to_dict(row)
    body["stats"] = _stats_for_book(conn, book_id)
    return body
```

Do NOT add stats to `list_books` — keep the list lean for filtering.

- [ ] **Step 2: Rescan endpoint**

Append to `studio_app/routes/books.py`:
```python
@router.post("/api/books/{book_id}/rescan_audio")
def rescan_audio(book_id: int, request: Request) -> dict:
    from studio_app.audio_scanner import scan_book, recompute_stats
    conn = request.app.state.conn
    row = conn.execute("SELECT id FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    count = scan_book(conn, book_id)
    recompute_stats(conn)
    return {"book_id": book_id, "audio_files": count}
```

- [ ] **Step 3: Tests**

Create `tests/test_routes_audio.py`:
```python
from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def _upload(client, tmp_path, title="X"):
    s = tmp_path / "x.txt"
    shutil.copy(FIXTURES / "sample.txt", s)
    with s.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("x.txt", fh, "text/plain")},
            data={"title": title},
        )
    return r.json()["id"]


async def test_get_book_includes_stats_block(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.get(f"/api/books/{bid}")
    assert r.status_code == 200
    body = r.json()
    assert "stats" in body
    assert body["stats"]["total_audio_seconds"] == 0


async def test_rescan_audio_with_no_folder_returns_zero(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.post(f"/api/books/{bid}/rescan_audio")
    assert r.status_code == 200
    assert r.json() == {"book_id": bid, "audio_files": 0}


async def test_rescan_audio_with_mp3_returns_count(client, tmp_path):
    bid = await _upload(client, tmp_path)
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch.mp3")
    await client.patch(f"/api/books/{bid}", json={"audio_folder": str(af)})
    r = await client.post(f"/api/books/{bid}/rescan_audio")
    body = r.json()
    assert body["audio_files"] == 1
    # And the book's stats block now reflects the scan.
    r2 = await client.get(f"/api/books/{bid}")
    assert r2.json()["stats"]["total_audio_seconds"] > 0


async def test_rescan_audio_404(client):
    r = await client.post("/api/books/9999/rescan_audio")
    assert r.status_code == 404
```

- [ ] **Step 4: Confirm pass**

Full suite: `uv run pytest -q` → expect 97 passed + 2 skipped (4 new tests).

- [ ] **Step 5: Commit**

```bash
git add studio_app/routes/books.py tests/test_routes_audio.py
git commit -m "feat(studio): book GET embeds stats; POST /rescan_audio endpoint"
```

---

## Task 6: Narrators GET embeds narrator_stats; UI history table

**Files:**
- Modify: `studio_app/routes/narrators.py` (embed stats + history)
- Modify: `tests/test_routes_narrators.py` (3 new tests)

This task also fixes the Phase-2 audit finding that `narrator.html`'s `#history-table` was unused.

- [ ] **Step 1: Failing tests**

Append to `tests/test_routes_narrators.py`:
```python


async def test_get_narrator_includes_stats_block(client):
    r = await client.post("/api/narrators", json={"name": "Stats Narr"})
    nid = r.json()["id"]
    r2 = await client.get(f"/api/narrators/{nid}")
    body = r2.json()
    assert "stats" in body
    assert body["stats"]["books_assigned"] == 0


async def test_get_narrator_includes_history_array(client):
    r = await client.post("/api/narrators", json={"name": "Hist Narr"})
    nid = r.json()["id"]
    r2 = await client.get(f"/api/narrators/{nid}")
    body = r2.json()
    assert "history" in body
    assert body["history"] == []
```

- [ ] **Step 2: Add `_stats_for_narrator` + `_history_for_narrator` helpers and update get_narrator**

In `studio_app/routes/narrators.py`, append helpers BEFORE the route definitions (just after the existing `_row`):

```python
def _stats_for_narrator(conn, narrator_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM narrator_stats WHERE narrator_id = ?", (narrator_id,)
    ).fetchone()
    if row is None:
        return {
            "books_assigned": 0,
            "books_done": 0,
            "total_audio_seconds": 0,
            "avg_chars_per_hour": 0,
            "avg_pages_per_hour": 0,
        }
    return {
        "books_assigned": row["books_assigned"],
        "books_done": row["books_done"],
        "total_audio_seconds": row["total_audio_seconds"],
        "avg_chars_per_hour": row["avg_chars_per_hour"],
        "avg_pages_per_hour": row["avg_pages_per_hour"],
    }


def _history_for_narrator(conn, narrator_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT nb.book_id, b.title, nb.assigned_at, nb.finished_at"
        " FROM narrator_book nb"
        " JOIN book b ON b.id = nb.book_id"
        " WHERE nb.narrator_id = ?"
        " ORDER BY nb.assigned_at DESC",
        (narrator_id,),
    ).fetchall()
    return [
        {
            "book_id": r["book_id"],
            "title": r["title"],
            "assigned_at": r["assigned_at"],
            "finished_at": r["finished_at"],
        }
        for r in rows
    ]
```

Replace `get_narrator`:
```python
@router.get("/api/narrators/{nid}")
def get_narrator(nid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Narrator not found")
    body = _row(row)
    body["stats"] = _stats_for_narrator(conn, nid)
    body["history"] = _history_for_narrator(conn, nid)
    return body
```

Do NOT add stats to `list_narrators` — keep the index lean.

- [ ] **Step 3: Confirm pass**

Full suite: 99 passed + 2 skipped (2 new tests).

- [ ] **Step 4: Commit**

```bash
git add studio_app/routes/narrators.py tests/test_routes_narrators.py
git commit -m "feat(studio): narrator GET embeds stats + history"
```

---

## Task 7: UI updates for stats + rescan button

**Files:**
- Modify: `studio_app/static/book.html` (stats cells)
- Modify: `studio_app/static/narrator.html` (stats panel + history rows)
- Modify: `studio_app/static/app.js` (render new fields; wire rescan button)

- [ ] **Step 1: book.html — add stats rows and rescan button**

Replace the existing "Stats" `<table>` block in `studio_app/static/book.html`:

```html
  <h2>Stats <button id="rescan-audio" type="button" style="font-size:12px; margin-left:8px">Re-scan audio</button>
  <span id="rescan-status" class="muted"></span></h2>
  <table>
    <tr><th>Format</th><td id="format"></td></tr>
    <tr><th>Pages</th><td id="pages"></td></tr>
    <tr><th>Body chars</th><td id="body_chars"></td></tr>
    <tr><th>Chars / page</th><td id="cpp"></td></tr>
    <tr><th>Hours recorded</th><td id="h_recorded">—</td></tr>
    <tr><th>Chars / hour</th><td id="chars_per_hour">—</td></tr>
    <tr><th>Pages / hour</th><td id="pages_per_hour">—</td></tr>
    <tr><th>Progress</th><td id="progress_pct">—</td></tr>
  </table>
```

- [ ] **Step 2: narrator.html — wire #history-table data and stats**

Replace the `<h2>Current work</h2>` ... `</main>` region with:

```html
  <h2>Stats</h2>
  <table>
    <tr><th>Books assigned</th><td id="s-assigned">0</td></tr>
    <tr><th>Books done</th><td id="s-done">0</td></tr>
    <tr><th>Hours recorded</th><td id="s-hours">—</td></tr>
    <tr><th>Avg chars / hour</th><td id="s-cph">—</td></tr>
    <tr><th>Avg pages / hour</th><td id="s-pph">—</td></tr>
  </table>
  <h2>Current work</h2>
  <table id="current-table">
    <thead><tr><th>Title</th><th>Progress</th><th>Planned end</th></tr></thead>
    <tbody><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
  </table>
  <h2>Assignment history</h2>
  <table id="history-table">
    <thead><tr><th>Book</th><th>Assigned</th><th>Finished</th></tr></thead>
    <tbody><tr><td colspan="3" class="muted">—</td></tr></tbody>
  </table>
</main>
```

- [ ] **Step 3: app.js — render stats + history, wire rescan button**

In `setupBookPage`, AFTER the existing `cpp` line, add stats rendering:

```javascript
  function fmtHours(seconds) { return seconds > 0 ? (seconds / 3600).toFixed(2) : '—'; }
  function fmtRound(x) { return x > 0 ? Math.round(x).toLocaleString() : '—'; }
  function fmtPct(x) { return x > 0 ? (x * 100).toFixed(1) + '%' : '—'; }

  const stats = b.stats || {};
  document.getElementById('h_recorded').textContent = fmtHours(stats.total_audio_seconds || 0);
  document.getElementById('chars_per_hour').textContent = fmtRound(stats.chars_per_hour || 0);
  document.getElementById('pages_per_hour').textContent = fmtRound(stats.pages_per_hour || 0);
  document.getElementById('progress_pct').textContent = fmtPct(stats.progress_pct || 0);

  document.getElementById('rescan-audio').addEventListener('click', async () => {
    const status = document.getElementById('rescan-status');
    status.textContent = 'Scanning…';
    try {
      const r = await jsonFetch(`/api/books/${id}/rescan_audio`, { method: 'POST' });
      status.textContent = `${r.audio_files} file(s).`;
      // Reload page to pick up fresh stats.
      const refreshed = await jsonFetch(`/api/books/${id}`);
      const s = refreshed.stats;
      document.getElementById('h_recorded').textContent = fmtHours(s.total_audio_seconds);
      document.getElementById('chars_per_hour').textContent = fmtRound(s.chars_per_hour);
      document.getElementById('pages_per_hour').textContent = fmtRound(s.pages_per_hour);
      document.getElementById('progress_pct').textContent = fmtPct(s.progress_pct);
    } catch (e) { status.textContent = e.message; }
  });
```

In `setupNarratorPage`, REPLACE the existing block that fills `#current-table` with this expanded version. AFTER the `narrator-form` listener wiring, add:

```javascript
  const stats = n.stats || {};
  document.getElementById('s-assigned').textContent = stats.books_assigned || 0;
  document.getElementById('s-done').textContent = stats.books_done || 0;
  document.getElementById('s-hours').textContent =
    stats.total_audio_seconds > 0 ? (stats.total_audio_seconds / 3600).toFixed(2) : '—';
  document.getElementById('s-cph').textContent =
    stats.avg_chars_per_hour > 0 ? Math.round(stats.avg_chars_per_hour).toLocaleString() : '—';
  document.getElementById('s-pph').textContent =
    stats.avg_pages_per_hour > 0 ? Math.round(stats.avg_pages_per_hour).toLocaleString() : '—';

  const history = n.history || [];
  const histBody = document.querySelector('#history-table tbody');
  histBody.innerHTML = history.length
    ? history.map(h => `
      <tr onclick="location.href='/books/${h.book_id}'" style="cursor:pointer">
        <td>${escapeHtml(h.title)}</td>
        <td>${h.assigned_at || '—'}</td>
        <td>${h.finished_at || '<span class="muted">active</span>'}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="muted">No history yet.</td></tr>';
```

(Keep the existing `?narrator_id=${nid}` "Current work" block intact.)

- [ ] **Step 4: Confirm tests still green**

Full suite: 99 passed + 2 skipped (no test changes; UI-only).

- [ ] **Step 5: Manual smoke**

`uv run studio-app`:
1. Upload a book, set its `audio_folder` to a folder containing MP3s (or copy `tests/fixtures/silence.mp3` into a real folder under your data root).
2. Click "Re-scan audio" on the book detail page → status shows file count, hours-recorded fills in.
3. Open a narrator with active books → narrator stats and history panels populated.

- [ ] **Step 6: Commit**

```bash
git add studio_app/static/book.html studio_app/static/narrator.html studio_app/static/app.js
git commit -m "feat(studio): UI surfaces book + narrator stats; rescan button"
```

---

## Phase 3 done-criteria

- [ ] All tests green: `uv run pytest -q` → 99 passed + 2 skipped.
- [ ] `uv run studio-app` boots; background AudioScanner runs.
- [ ] `GET /api/heartbeat` includes `last_audio_scan_at`.
- [ ] Upload a book + point at audio folder + click "Re-scan audio" → stats fill in within seconds.
- [ ] Narrator detail shows assignment history derived from `narrator_book`.
- [ ] Schema unchanged from Phase 2 (no migrations required).

## Self-review

| Spec section | Where it lands |
|---|---|
| §3.1 audio scanner background job | Tasks 3 + 4 |
| §4 audio_file table population | Task 1 |
| §4 book_stats / narrator_stats recompute | Tasks 1 + 2 |
| §6.1 Stats panel + Re-scan button | Tasks 5 + 7 |
| §6.3 Narrator stats card + history | Tasks 6 + 7 |
| Phase 2 audit gap: narrator history UI never populated | Task 7 |
| Phase 2 audit gap: no `GET /api/narrators/:id/history` | Task 6 |

**Deferred to Phase 4:**
- Snapshot job (DB → data_root); audio scan + snapshot share the same daemon strategy.
- Calendar ICS poller (also a daemon thread).
- Session reaper (depends on reading_session lifecycle from Phase 4).

No placeholders. Every code step shows actual code.
