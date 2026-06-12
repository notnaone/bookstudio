# Phase 1 — Foundation & Book Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the FastAPI app skeleton with SQLite schema, settings (data_root + first-run wizard), parser integration, and a minimal library page that lists books ingested via file upload. End state: user can drop a PDF/EPUB/DOCX/TXT into the app and see it on the library page; state survives restart.

**Architecture:** Single FastAPI process serving JSON API + static HTML. SQLite in WAL mode under a user-chosen `data_root`. Existing `book_analyzer` package is imported and called from the ingest pipeline. No background threads yet (Phase 3 adds the scanner). No viewer yet (Phase 4).

**Tech Stack:**
- Python 3.11+, FastAPI, Uvicorn
- SQLite via `sqlite3` stdlib (no ORM in Phase 1)
- pytest + httpx.AsyncClient for tests
- Existing `book_analyzer` package (PDF/EPUB/DOCX/TXT parser, already in repo)
- Vanilla JS + plain HTML/CSS, no bundler

---

## File structure

**New files:**
```
studio_app/
├── __init__.py
├── main.py                    # FastAPI app factory + dev server entrypoint
├── settings.py                # AppSettings dataclass, load/save via app_setting table
├── db.py                      # connect(), migrate(), tx() context manager
├── slug.py                    # slugify(title) → URL/fs-safe slug
├── ingest.py                  # ingest_book(source_path) → book row
├── parser_adapter.py          # thin adapter: call book_analyzer.parse() → dict
├── routes/
│   ├── __init__.py
│   ├── books.py               # GET/POST /api/books, GET /api/books/:id
│   ├── settings_routes.py     # GET/PATCH /api/settings, POST /api/setup
│   └── system.py              # GET /api/heartbeat
├── migrations/
│   └── 001_initial.sql        # full schema from spec §4
└── static/
    ├── index.html             # redirect to /library or /setup
    ├── setup.html             # first-run wizard
    ├── library.html           # books table
    ├── book.html              # book detail
    ├── app.js                 # vanilla JS for forms + fetch
    └── styles.css

tests/
├── conftest.py                # tmp_path-based data_root fixture, app fixture
├── test_db.py
├── test_settings.py
├── test_slug.py
├── test_parser_adapter.py
├── test_ingest.py
├── test_routes_books.py
├── test_routes_settings.py
└── fixtures/
    ├── sample.txt
    └── sample.docx            # tiny generated samples
```

**Modified files:**
- `pyproject.toml` — add `fastapi`, `uvicorn[standard]`, `pytest`, `pytest-asyncio`, `httpx` to deps; add `studio-app` script entry.

---

## Task 0: Bootstrap dependencies and package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `studio_app/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py` (stub)

- [ ] **Step 1: Add dependencies to pyproject.toml**

Open `pyproject.toml`. In `[project].dependencies` add (keep existing entries):
```toml
"fastapi>=0.115.0",
"uvicorn[standard]>=0.32.0",
"jinja2>=3.1.4",
```

Add a new section after `[project.optional-dependencies]`:
```toml
[dependency-groups]
dev = [
  "pytest>=8.0",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
]
```

In `[project.scripts]` add a new line:
```toml
studio-app = "studio_app.main:main"
```

- [ ] **Step 2: Install**

Run:
```bash
uv sync --all-groups
```
Expected: success, virtualenv updated.

- [ ] **Step 3: Create the package skeleton**

Create `studio_app/__init__.py`:
```python
"""Audiobook studio management web application."""
__version__ = "0.1.0"
```

Create `tests/__init__.py` as an empty file.

Create `tests/conftest.py`:
```python
from __future__ import annotations

import pytest
```

- [ ] **Step 4: Verify pytest collects nothing yet**

Run:
```bash
uv run pytest -q
```
Expected: `no tests ran`, exit 5 is fine.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml studio_app/__init__.py tests/__init__.py tests/conftest.py
git commit -m "feat(studio): bootstrap package + dev dependencies"
```

---

## Task 1: Slug generator

**Files:**
- Create: `studio_app/slug.py`
- Test: `tests/test_slug.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_slug.py`:
```python
from __future__ import annotations

from studio_app.slug import slugify


def test_slugify_basic():
    assert slugify("Hello World") == "hello-world"


def test_slugify_strips_punctuation():
    assert slugify("Chris - SciFi: Project!") == "chris-scifi-project"


def test_slugify_collapses_whitespace():
    assert slugify("  many   spaces  ") == "many-spaces"


def test_slugify_unicode_transliteration():
    assert slugify("Café Olé") == "cafe-ole"


def test_slugify_empty_returns_book():
    assert slugify("") == "book"


def test_slugify_max_length_60():
    s = slugify("a" * 200)
    assert len(s) <= 60
    assert s == "a" * 60
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/test_slug.py -v
```
Expected: ImportError (module missing).

- [ ] **Step 3: Implement**

Create `studio_app/slug.py`:
```python
from __future__ import annotations

import re
import unicodedata

MAX_LEN = 60


def slugify(title: str) -> str:
    """Return a filesystem- and URL-safe slug from `title`."""
    if not title or not title.strip():
        return "book"
    # Decompose accented chars (Café → Cafe).
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    # Replace any run of non-alphanumeric with a single hyphen.
    s = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if not s:
        return "book"
    return s[:MAX_LEN]
```

- [ ] **Step 4: Run, confirm pass**

```bash
uv run pytest tests/test_slug.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add studio_app/slug.py tests/test_slug.py
git commit -m "feat(studio): add slugify"
```

---

## Task 2: SQLite migration runner

**Files:**
- Create: `studio_app/db.py`
- Create: `studio_app/migrations/001_initial.sql`
- Test: `tests/test_db.py`

- [ ] **Step 1: Write the full initial schema**

Create `studio_app/migrations/001_initial.sql`. Paste the entire DDL from the spec §4. Reproduced here verbatim for self-containment:

```sql
-- 1. Publisher
CREATE TABLE publisher (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  notes TEXT
);

-- 2. Narrator
CREATE TABLE narrator (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  calendar_alias TEXT UNIQUE,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Book
CREATE TABLE book (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  publisher_id INTEGER,
  source_path TEXT NOT NULL,
  view_path TEXT NOT NULL,
  format TEXT NOT NULL,
  genre TEXT,
  publisher_notes TEXT,
  body_chars INTEGER DEFAULT 0,
  raw_chars INTEGER DEFAULT 0,
  chars_per_page INTEGER DEFAULT 0,
  pages INTEGER DEFAULT 0,
  images INTEGER DEFAULT 0,
  charts_tables INTEGER DEFAULT 0,
  audio_folder TEXT,
  drive_sync_path TEXT,
  narrator_id INTEGER,
  planned_end DATE,
  current_page INTEGER DEFAULT 1,
  status TEXT CHECK(status IN ('planned','in_progress','done','archived')) DEFAULT 'planned',
  is_draft INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (publisher_id) REFERENCES publisher(id),
  FOREIGN KEY (narrator_id)  REFERENCES narrator(id)
);

CREATE TRIGGER book_touch AFTER UPDATE ON book BEGIN
  UPDATE book SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 4. Narrator-book assignment history
CREATE TABLE narrator_book (
  narrator_id INTEGER,
  book_id     INTEGER,
  assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME,
  PRIMARY KEY (narrator_id, book_id),
  FOREIGN KEY (narrator_id) REFERENCES narrator(id),
  FOREIGN KEY (book_id)     REFERENCES book(id)
);

-- 5. Schedule items (declared before reading_session so FK target exists)
CREATE TABLE schedule_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT CHECK(source IN ('studio_1','studio_2','manual')) NOT NULL,
  google_event_id TEXT UNIQUE,
  start_time DATETIME NOT NULL,
  end_time   DATETIME NOT NULL,
  raw_title TEXT NOT NULL,
  notes     TEXT,
  resolved_narrator_id INTEGER,
  resolved_book_id     INTEGER,
  resolved_at DATETIME,
  action_status TEXT CHECK(action_status IN
    ('pending','started','completed','skipped','cancelled')
  ) DEFAULT 'pending',
  kind TEXT CHECK(kind IN ('recording','editing','deadline')),
  last_synced_at DATETIME,
  FOREIGN KEY (resolved_narrator_id) REFERENCES narrator(id),
  FOREIGN KEY (resolved_book_id)     REFERENCES book(id)
);

-- 6. Reading session
CREATE TABLE reading_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,
  start_page INTEGER NOT NULL,
  end_page   INTEGER,
  tracked_progress_page INTEGER,
  active_seconds INTEGER DEFAULT 0,
  last_heartbeat_at DATETIME,
  auto_closed INTEGER DEFAULT 0,
  schedule_item_id INTEGER,
  FOREIGN KEY (book_id)          REFERENCES book(id),
  FOREIGN KEY (narrator_id)      REFERENCES narrator(id),
  FOREIGN KEY (schedule_item_id) REFERENCES schedule_item(id)
);

-- 7. Work session
CREATE TABLE work_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,
  kind TEXT CHECK(kind IN ('recording','editing')) NOT NULL,
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,
  start_page INTEGER,
  end_page   INTEGER,
  notes TEXT,
  FOREIGN KEY (book_id)     REFERENCES book(id),
  FOREIGN KEY (narrator_id) REFERENCES narrator(id)
);

-- 8. Audio file
CREATE TABLE audio_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id         INTEGER NOT NULL,
  work_session_id INTEGER,
  path     TEXT NOT NULL,
  filename TEXT NOT NULL,
  duration_seconds REAL DEFAULT 0,
  size_bytes INTEGER DEFAULT 0,
  mtime DATETIME,
  scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id)         REFERENCES book(id),
  FOREIGN KEY (work_session_id) REFERENCES work_session(id)
);

-- 9. Marks
CREATE TABLE mark (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id INTEGER NOT NULL,
  page INTEGER NOT NULL,
  x_pct REAL NOT NULL,
  y_pct REAL NOT NULL,
  w_pct REAL NOT NULL,
  h_pct REAL NOT NULL,
  color TEXT DEFAULT '#FFFF00',
  comment TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id) REFERENCES book(id)
);

-- 10. Derived stats
CREATE TABLE book_stats (
  book_id INTEGER PRIMARY KEY,
  total_audio_seconds REAL DEFAULT 0,
  chars_per_hour REAL DEFAULT 0,
  pages_per_hour REAL DEFAULT 0,
  progress_pct REAL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id) REFERENCES book(id)
);

CREATE TABLE narrator_stats (
  narrator_id INTEGER PRIMARY KEY,
  books_assigned INTEGER DEFAULT 0,
  books_done INTEGER DEFAULT 0,
  total_audio_seconds REAL DEFAULT 0,
  avg_chars_per_hour REAL DEFAULT 0,
  avg_pages_per_hour REAL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (narrator_id) REFERENCES narrator(id)
);

-- 11. App settings
CREATE TABLE app_setting (
  key TEXT PRIMARY KEY,
  value TEXT
);

-- Indexes
CREATE INDEX idx_book_status     ON book(status);
CREATE INDEX idx_book_narrator   ON book(narrator_id);
CREATE INDEX idx_sched_time      ON schedule_item(start_time);
CREATE INDEX idx_sched_status    ON schedule_item(action_status, start_time);
CREATE INDEX idx_rsess_book      ON reading_session(book_id, started_at);
CREATE INDEX idx_rsess_open      ON reading_session(ended_at) WHERE ended_at IS NULL;
CREATE INDEX idx_wsess_book      ON work_session(book_id, started_at);
CREATE INDEX idx_audio_book      ON audio_file(book_id);
CREATE INDEX idx_mark_book_page  ON mark(book_id, page);

-- Schema version marker
INSERT INTO app_setting (key, value) VALUES ('schema_version', '1');
```

- [ ] **Step 2: Write failing db tests**

Create `tests/test_db.py`:
```python
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
    migrate(db_path)  # second call must not raise
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
```

- [ ] **Step 3: Run, confirm failure**

```bash
uv run pytest tests/test_db.py -v
```
Expected: ImportError (db module missing).

- [ ] **Step 4: Implement db.py**

Create `studio_app/db.py`:
```python
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
        conn.executescript(sql)
    conn.close()
```

- [ ] **Step 5: Run, confirm pass**

```bash
uv run pytest tests/test_db.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add studio_app/db.py studio_app/migrations/001_initial.sql tests/test_db.py
git commit -m "feat(studio): sqlite schema migration runner"
```

---

## Task 3: Settings module

**Files:**
- Create: `studio_app/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_settings.py`:
```python
from __future__ import annotations

from pathlib import Path

from studio_app.db import connect, migrate
from studio_app.settings import (
    REQUIRED_KEYS,
    AppSettings,
    is_configured,
    load,
    save_key,
)


def make_conn(tmp_path: Path):
    db = tmp_path / "studio.live.sqlite"
    migrate(db)
    return connect(db)


def test_load_returns_empty_when_no_settings(tmp_path: Path):
    conn = make_conn(tmp_path)
    s = load(conn)
    assert s.data_root is None
    assert s.pace_unit == "chars_per_hour"  # default fallback


def test_save_and_load_data_root(tmp_path: Path):
    conn = make_conn(tmp_path)
    save_key(conn, "data_root", str(tmp_path / "root"))
    s = load(conn)
    assert s.data_root == str(tmp_path / "root")


def test_is_configured_requires_data_root(tmp_path: Path):
    conn = make_conn(tmp_path)
    assert not is_configured(conn)
    save_key(conn, "data_root", str(tmp_path / "root"))
    assert is_configured(conn)


def test_required_keys_present():
    assert "data_root" in REQUIRED_KEYS


def test_save_key_overwrites(tmp_path: Path):
    conn = make_conn(tmp_path)
    save_key(conn, "pace_unit", "pages_per_hour")
    save_key(conn, "pace_unit", "chars_per_hour")
    s = load(conn)
    assert s.pace_unit == "chars_per_hour"


def test_appsettings_default_intervals():
    s = AppSettings()
    assert s.snapshot_interval_seconds == 300
    assert s.audio_scan_interval_seconds == 300
    assert s.calendar_poll_interval_seconds == 300
    assert s.reaper_interval_seconds == 60
    assert s.session_idle_timeout_seconds == 300
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/test_settings.py -v
```
Expected: ImportError.

- [ ] **Step 3: Implement settings.py**

Create `studio_app/settings.py`:
```python
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

REQUIRED_KEYS = ("data_root",)

_DEFAULTS = {
    "pace_unit": "chars_per_hour",
    "snapshot_interval_seconds": "300",
    "audio_scan_interval_seconds": "300",
    "calendar_poll_interval_seconds": "300",
    "reaper_interval_seconds": "60",
    "session_idle_timeout_seconds": "300",
}


@dataclass
class AppSettings:
    data_root: str | None = None
    local_state_dir: str | None = None
    ics_url_studio_1: str | None = None
    ics_url_studio_2: str | None = None
    pace_unit: str = "chars_per_hour"
    snapshot_interval_seconds: int = 300
    audio_scan_interval_seconds: int = 300
    calendar_poll_interval_seconds: int = 300
    reaper_interval_seconds: int = 60
    session_idle_timeout_seconds: int = 300


def load(conn: sqlite3.Connection) -> AppSettings:
    rows = conn.execute("SELECT key, value FROM app_setting").fetchall()
    raw = {r["key"]: r["value"] for r in rows}
    merged = {**_DEFAULTS, **raw}
    return AppSettings(
        data_root=merged.get("data_root"),
        local_state_dir=merged.get("local_state_dir"),
        ics_url_studio_1=merged.get("ics_url_studio_1"),
        ics_url_studio_2=merged.get("ics_url_studio_2"),
        pace_unit=merged.get("pace_unit", "chars_per_hour"),
        snapshot_interval_seconds=int(merged.get("snapshot_interval_seconds", 300)),
        audio_scan_interval_seconds=int(merged.get("audio_scan_interval_seconds", 300)),
        calendar_poll_interval_seconds=int(merged.get("calendar_poll_interval_seconds", 300)),
        reaper_interval_seconds=int(merged.get("reaper_interval_seconds", 60)),
        session_idle_timeout_seconds=int(merged.get("session_idle_timeout_seconds", 300)),
    )


def save_key(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def is_configured(conn: sqlite3.Connection) -> bool:
    s = load(conn)
    return s.data_root is not None and s.data_root != ""
```

- [ ] **Step 4: Run, confirm pass**

```bash
uv run pytest tests/test_settings.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add studio_app/settings.py tests/test_settings.py
git commit -m "feat(studio): app settings backed by app_setting table"
```

---

## Task 4: Parser adapter

**Files:**
- Create: `studio_app/parser_adapter.py`
- Test: `tests/test_parser_adapter.py`
- Create: `tests/fixtures/sample.txt`

- [ ] **Step 1: Create the fixture**

Create `tests/fixtures/sample.txt`:
```
Chapter 1

This is a test paragraph. It has several sentences. The parser should
count visible characters and ignore whitespace.

Chapter 2

Another paragraph in another chapter. This lets us verify chapter counting.
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_parser_adapter.py`:
```python
from __future__ import annotations

from pathlib import Path

from studio_app.parser_adapter import ParsedBook, parse_book

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_book_txt_returns_parsedbook():
    result = parse_book(FIXTURES / "sample.txt")
    assert isinstance(result, ParsedBook)
    assert result.format == "txt"
    assert result.body_chars > 0
    assert result.raw_chars >= result.body_chars


def test_parse_book_includes_chapters():
    result = parse_book(FIXTURES / "sample.txt")
    assert result.total_chapters >= 1


def test_parse_book_unknown_format_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_book(FIXTURES / "sample.xyz")
```

- [ ] **Step 3: Run, confirm failure**

```bash
uv run pytest tests/test_parser_adapter.py -v
```
Expected: ImportError.

- [ ] **Step 4: Implement parser_adapter.py**

Create `studio_app/parser_adapter.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from book_analyzer.parsers import get_parser


@dataclass
class ParsedBook:
    format: str
    body_chars: int
    raw_chars: int
    total_paragraphs: int
    total_chapters: int
    total_images: int
    total_tables: int
    total_charts: int
    total_pages: int | None
    offset_reliability: str

    @property
    def chars_per_page(self) -> int:
        if not self.total_pages or self.total_pages == 0:
            return 0
        return self.body_chars // self.total_pages


def parse_book(source_path: Path) -> ParsedBook:
    """Run book_analyzer over `source_path` and return a flat result."""
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    try:
        parser = get_parser(source_path)
    except Exception as exc:
        raise ValueError(f"Unsupported format: {source_path.suffix}") from exc
    result = parser.parse()
    m = result.book_metadata
    return ParsedBook(
        format=m.file_format,
        body_chars=m.body_character_count,
        raw_chars=m.raw_character_count,
        total_paragraphs=m.total_paragraphs,
        total_chapters=m.total_chapters,
        total_images=m.total_images,
        total_tables=m.total_tables,
        total_charts=m.total_charts,
        total_pages=m.total_pages,
        offset_reliability=m.offset_reliability,
    )
```

- [ ] **Step 5: Run, confirm pass**

```bash
uv run pytest tests/test_parser_adapter.py -v
```
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add studio_app/parser_adapter.py tests/test_parser_adapter.py tests/fixtures/sample.txt
git commit -m "feat(studio): parser_adapter wraps book_analyzer for service use"
```

---

## Task 5: Book ingest pipeline

**Files:**
- Create: `studio_app/ingest.py`
- Test: `tests/test_ingest.py`
- Modify: `tests/conftest.py` (add `data_root` and `conn` fixtures)

- [ ] **Step 1: Add fixtures to conftest.py**

Replace `tests/conftest.py` with:
```python
from __future__ import annotations

from pathlib import Path

import pytest

from studio_app.db import connect, migrate


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    root.mkdir()
    (root / "books").mkdir()
    (root / "exports").mkdir()
    return root


@pytest.fixture
def local_state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "local_state"
    d.mkdir()
    return d


@pytest.fixture
def conn(local_state_dir: Path):
    db = local_state_dir / "studio.live.sqlite"
    migrate(db)
    c = connect(db)
    yield c
    c.close()
```

- [ ] **Step 2: Write failing tests**

Create `tests/test_ingest.py`:
```python
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


def test_ingest_book_sets_view_path_for_pdf(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "fake.pdf"
    src.write_bytes(b"%PDF-1.4 not real")  # parser will fail; we don't ingest this one
    pytest.skip("PDF fixture not yet available; covered by Phase 4 integration test")


def test_ingest_book_creates_metadata_json(conn, data_root: Path, tmp_path: Path):
    src = tmp_path / "incoming.txt"
    shutil.copy(FIXTURES / "sample.txt", src)
    book_id = ingest_book(conn, data_root, src, title="Sample Book")
    meta = data_root / "books" / "sample-book" / "metadata.json"
    assert meta.exists()
    text = meta.read_text(encoding="utf-8")
    assert "body_chars" in text or "body_character_count" in text


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
```

- [ ] **Step 3: Run, confirm failure**

```bash
uv run pytest tests/test_ingest.py -v
```
Expected: ImportError.

- [ ] **Step 4: Implement ingest.py**

Create `studio_app/ingest.py`:
```python
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from studio_app.parser_adapter import parse_book
from studio_app.slug import slugify


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    candidate = base
    n = 2
    while conn.execute(
        "SELECT 1 FROM book WHERE slug = ?", (candidate,)
    ).fetchone() is not None:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def ingest_book(
    conn: sqlite3.Connection,
    data_root: Path,
    source_file: Path,
    *,
    title: str,
    publisher_id: int | None = None,
    audio_folder: str | None = None,
    is_draft: bool = False,
) -> int:
    """Copy `source_file` into the data_root, parse it, insert a book row.

    Returns the new book.id.
    """
    if not source_file.exists():
        raise FileNotFoundError(source_file)

    base_slug = slugify(title)
    slug = _unique_slug(conn, base_slug)

    book_dir = data_root / "books" / slug
    src_dir = book_dir / "source"
    view_dir = book_dir / "view"
    src_dir.mkdir(parents=True, exist_ok=True)
    view_dir.mkdir(parents=True, exist_ok=True)

    dest = src_dir / source_file.name
    shutil.copy2(source_file, dest)

    # Parse (raises ValueError on unknown format).
    try:
        parsed = parse_book(dest)
    except ValueError:
        # Roll back the copy so the data_root stays clean.
        shutil.rmtree(book_dir, ignore_errors=True)
        raise

    # Persist parser output to disk for human inspection.
    metadata_path = book_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "format": parsed.format,
                "body_chars": parsed.body_chars,
                "raw_chars": parsed.raw_chars,
                "total_paragraphs": parsed.total_paragraphs,
                "total_chapters": parsed.total_chapters,
                "total_images": parsed.total_images,
                "total_tables": parsed.total_tables,
                "total_charts": parsed.total_charts,
                "total_pages": parsed.total_pages,
                "offset_reliability": parsed.offset_reliability,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # For PDF and EPUB, view_path == source_path (Phase 1; viewer is Phase 4).
    # For DOCX/TXT, view pagination is Phase 4. Phase 1 stores the source path
    # as a placeholder; the viewer adapter handles the real layout later.
    view_path = str(dest)

    cur = conn.execute(
        """
        INSERT INTO book (
            slug, title, publisher_id, source_path, view_path, format,
            body_chars, raw_chars, chars_per_page, pages,
            images, charts_tables,
            audio_folder, is_draft, current_page, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'planned')
        """,
        (
            slug, title, publisher_id,
            str(dest), view_path, parsed.format,
            parsed.body_chars, parsed.raw_chars,
            parsed.chars_per_page, parsed.total_pages or 0,
            parsed.total_images, parsed.total_tables + parsed.total_charts,
            audio_folder, 1 if is_draft else 0,
        ),
    )
    return int(cur.lastrowid)
```

- [ ] **Step 5: Run, confirm pass**

```bash
uv run pytest tests/test_ingest.py -v
```
Expected: 5 passed (with one explicitly skipped).

- [ ] **Step 6: Commit**

```bash
git add studio_app/ingest.py tests/test_ingest.py tests/conftest.py
git commit -m "feat(studio): book ingest pipeline copies, parses, persists"
```

---

## Task 6: FastAPI app factory + system route

**Files:**
- Create: `studio_app/main.py`
- Create: `studio_app/routes/__init__.py`
- Create: `studio_app/routes/system.py`
- Modify: `tests/conftest.py` (add `client` fixture)
- Test: `tests/test_routes_system.py`

- [ ] **Step 1: Add the `client` fixture**

Append to `tests/conftest.py`:
```python


from httpx import ASGITransport, AsyncClient

from studio_app.main import build_app


@pytest.fixture
def app(conn, data_root: Path, local_state_dir: Path):
    # Pre-seed data_root setting so routes that need it don't hit the wizard.
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('data_root', ?)",
        (str(data_root),),
    )
    return build_app(conn=conn, data_root=data_root, local_state_dir=local_state_dir)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

Add to the top of `tests/conftest.py` (after existing imports):
```python
import asyncio  # noqa: F401  (pytest-asyncio uses it)
```

Configure `pytest-asyncio` mode. Create `pyproject.toml` entry under `[tool.pytest.ini_options]`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2: Write failing test**

Create `tests/test_routes_system.py`:
```python
from __future__ import annotations


async def test_heartbeat_returns_status(client):
    r = await client.get("/api/heartbeat")
    assert r.status_code == 200
    body = r.json()
    assert "active_sessions" in body
    assert body["active_sessions"] == 0
```

- [ ] **Step 3: Run, confirm failure**

```bash
uv run pytest tests/test_routes_system.py -v
```
Expected: ImportError on `studio_app.main`.

- [ ] **Step 4: Implement routes/system.py**

Create `studio_app/routes/__init__.py` as an empty file.

Create `studio_app/routes/system.py`:
```python
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/heartbeat")
def heartbeat(request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM reading_session WHERE ended_at IS NULL"
    ).fetchone()
    return {
        "active_sessions": int(row["c"]),
        "last_snapshot_at": None,
        "last_calendar_sync_at": None,
    }
```

- [ ] **Step 5: Implement main.py**

Create `studio_app/main.py`:
```python
from __future__ import annotations

import sqlite3
import sys
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from studio_app.db import connect, migrate
from studio_app.routes import system as system_routes

STATIC_DIR = Path(__file__).parent / "static"
DEFAULT_LOCAL_STATE_DIR = Path.home() / "AppData" / "Roaming" / "StudioApp"


def build_app(
    *,
    conn: sqlite3.Connection,
    data_root: Path,
    local_state_dir: Path,
) -> FastAPI:
    app = FastAPI(title="Studio App")
    app.state.conn = conn
    app.state.data_root = data_root
    app.state.local_state_dir = local_state_dir
    app.include_router(system_routes.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _resolve_local_state_dir() -> Path:
    return Path(DEFAULT_LOCAL_STATE_DIR)


def main() -> int:
    local_state_dir = _resolve_local_state_dir()
    local_state_dir.mkdir(parents=True, exist_ok=True)
    db_path = local_state_dir / "studio.live.sqlite"
    migrate(db_path)
    conn = connect(db_path)
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key='data_root'"
    ).fetchone()
    data_root = Path(row["value"]) if row and row["value"] else local_state_dir / "tmp_data_root"
    data_root.mkdir(parents=True, exist_ok=True)
    app = build_app(conn=conn, data_root=data_root, local_state_dir=local_state_dir)
    url = "http://127.0.0.1:8765"
    print(f"Studio App running at {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Also create `studio_app/static/index.html` as a one-liner so StaticFiles mount is happy:
```html
<!doctype html><meta charset="utf-8"><title>Studio App</title>
<script>location.href="/library"</script>
```

- [ ] **Step 6: Run, confirm pass**

```bash
uv run pytest tests/test_routes_system.py -v
```
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add studio_app/main.py studio_app/routes/__init__.py studio_app/routes/system.py studio_app/static/index.html tests/conftest.py tests/test_routes_system.py pyproject.toml
git commit -m "feat(studio): FastAPI app factory + /api/heartbeat"
```

---

## Task 7: Books API routes

**Files:**
- Create: `studio_app/routes/books.py`
- Modify: `studio_app/main.py` (mount router)
- Test: `tests/test_routes_books.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes_books.py`:
```python
from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def test_get_books_empty(client):
    r = await client.get("/api/books")
    assert r.status_code == 200
    assert r.json() == {"books": []}


async def test_post_book_uploads_and_lists(client, tmp_path: Path):
    sample = tmp_path / "upload.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("upload.txt", fh, "text/plain")},
            data={"title": "Uploaded Book"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Uploaded Book"
    assert body["slug"] == "uploaded-book"
    assert body["body_chars"] > 0

    r2 = await client.get("/api/books")
    rows = r2.json()["books"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Uploaded Book"


async def test_get_book_by_id(client, tmp_path: Path):
    sample = tmp_path / "u.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("u.txt", fh, "text/plain")},
            data={"title": "Detail Book"},
        )
    book_id = r.json()["id"]
    r2 = await client.get(f"/api/books/{book_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == book_id
    assert body["title"] == "Detail Book"


async def test_post_book_rejects_unsupported_format(client, tmp_path: Path):
    bad = tmp_path / "thing.xyz"
    bad.write_bytes(b"nope")
    with bad.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("thing.xyz", fh, "application/octet-stream")},
            data={"title": "Bad Format"},
        )
    assert r.status_code == 400
    assert "unsupported" in r.json()["detail"].lower()


async def test_get_book_404(client):
    r = await client.get("/api/books/9999")
    assert r.status_code == 404
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/test_routes_books.py -v
```
Expected: 404 / module-missing failures.

- [ ] **Step 3: Implement routes/books.py**

Create `studio_app/routes/books.py`:
```python
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from studio_app.ingest import ingest_book

router = APIRouter()


def _book_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "title": row["title"],
        "format": row["format"],
        "body_chars": row["body_chars"],
        "raw_chars": row["raw_chars"],
        "chars_per_page": row["chars_per_page"],
        "pages": row["pages"],
        "images": row["images"],
        "charts_tables": row["charts_tables"],
        "status": row["status"],
        "is_draft": row["is_draft"],
        "current_page": row["current_page"],
        "publisher_id": row["publisher_id"],
        "narrator_id": row["narrator_id"],
        "planned_end": row["planned_end"],
        "audio_folder": row["audio_folder"],
        "source_path": row["source_path"],
        "view_path": row["view_path"],
    }


@router.get("/api/books")
def list_books(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute(
        "SELECT * FROM book ORDER BY updated_at DESC"
    ).fetchall()
    return {"books": [_book_row_to_dict(r) for r in rows]}


@router.get("/api/books/{book_id}")
def get_book(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return _book_row_to_dict(row)


@router.post("/api/books", status_code=201)
async def create_book(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
) -> dict:
    conn = request.app.state.conn
    data_root: Path = request.app.state.data_root

    # Stream upload to a temp file so the parser sees a real Path.
    suffix = Path(file.filename or "").suffix or ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        chunk = await file.read()
        tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        book_id = ingest_book(conn, data_root, tmp_path, title=title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported file: {exc}") from exc
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass

    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)
```

- [ ] **Step 4: Mount the router**

Edit `studio_app/main.py`. In the `build_app` function add:
```python
from studio_app.routes import books as books_routes  # at top with other imports
...
app.include_router(books_routes.router)  # after the system_routes line
```

- [ ] **Step 5: Run, confirm pass**

```bash
uv run pytest tests/test_routes_books.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add studio_app/routes/books.py studio_app/main.py tests/test_routes_books.py
git commit -m "feat(studio): books API — list, get, upload+ingest"
```

---

## Task 8: Settings route + first-run wizard JSON API

**Files:**
- Create: `studio_app/routes/settings_routes.py`
- Modify: `studio_app/main.py` (mount router; redirect when unconfigured)
- Test: `tests/test_routes_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_routes_settings.py`:
```python
from __future__ import annotations

from pathlib import Path


async def test_get_settings_returns_current(client):
    r = await client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    assert "data_root" in body
    assert body["pace_unit"] == "chars_per_hour"


async def test_patch_settings_updates_value(client):
    r = await client.patch("/api/settings", json={"pace_unit": "pages_per_hour"})
    assert r.status_code == 200
    assert r.json()["pace_unit"] == "pages_per_hour"


async def test_post_setup_initializes_data_root(client, tmp_path: Path):
    new_root = tmp_path / "fresh_root"
    r = await client.post("/api/setup", json={"data_root": str(new_root)})
    assert r.status_code == 200
    assert r.json()["data_root"] == str(new_root)
    assert (new_root / "books").is_dir()
    assert (new_root / "exports").is_dir()


async def test_post_setup_rejects_blank_data_root(client):
    r = await client.post("/api/setup", json={"data_root": "  "})
    assert r.status_code == 400
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/test_routes_settings.py -v
```
Expected: 404 on missing endpoints.

- [ ] **Step 3: Implement settings_routes.py**

Create `studio_app/routes/settings_routes.py`:
```python
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from studio_app.settings import load, save_key

router = APIRouter()


@router.get("/api/settings")
def get_settings(request: Request) -> dict:
    conn = request.app.state.conn
    return asdict(load(conn))


@router.patch("/api/settings")
async def patch_settings(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object required")
    allowed = {
        "data_root", "local_state_dir",
        "ics_url_studio_1", "ics_url_studio_2", "pace_unit",
        "snapshot_interval_seconds", "audio_scan_interval_seconds",
        "calendar_poll_interval_seconds", "reaper_interval_seconds",
        "session_idle_timeout_seconds",
    }
    for k, v in payload.items():
        if k not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown setting: {k}")
        save_key(conn, k, str(v))
    return asdict(load(conn))


@router.post("/api/setup")
async def setup(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    raw = (payload.get("data_root") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="data_root must be non-empty")
    new_root = Path(raw)
    new_root.mkdir(parents=True, exist_ok=True)
    (new_root / "books").mkdir(exist_ok=True)
    (new_root / "exports").mkdir(exist_ok=True)
    save_key(conn, "data_root", str(new_root))
    request.app.state.data_root = new_root
    return asdict(load(conn))
```

- [ ] **Step 4: Mount the router**

Edit `studio_app/main.py`. Add import:
```python
from studio_app.routes import settings_routes
```
And in `build_app`:
```python
app.include_router(settings_routes.router)
```

- [ ] **Step 5: Run, confirm pass**

```bash
uv run pytest tests/test_routes_settings.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add studio_app/routes/settings_routes.py studio_app/main.py tests/test_routes_settings.py
git commit -m "feat(studio): settings GET/PATCH + setup wizard endpoint"
```

---

## Task 9: Minimal HTML for setup wizard + library + book detail

**Files:**
- Create: `studio_app/static/setup.html`
- Create: `studio_app/static/library.html`
- Create: `studio_app/static/book.html`
- Create: `studio_app/static/app.js`
- Create: `studio_app/static/styles.css`
- Modify: `studio_app/main.py` (add HTML route fallbacks)

- [ ] **Step 1: Implement styles.css**

Create `studio_app/static/styles.css`:
```css
:root { --bg:#0f1115; --fg:#e6e8ed; --muted:#888c95; --accent:#5b8def; --border:#23262d; }
* { box-sizing: border-box; }
body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif;
       background:var(--bg); color:var(--fg); }
header { padding: 12px 24px; border-bottom: 1px solid var(--border); display:flex; gap:16px; align-items:center; }
header a { color: var(--fg); text-decoration: none; padding: 6px 10px; border-radius: 6px; }
header a.active { background: var(--border); }
main { padding: 24px; max-width: 1200px; margin: 0 auto; }
h1 { margin-top: 0; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }
th { color: var(--muted); font-weight: 600; }
button, input, select { font: inherit; color: inherit; background: #1a1d23; border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; }
button { cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.muted { color: var(--muted); }
.row { display: flex; gap: 12px; align-items: center; }
.col { display: flex; flex-direction: column; gap: 8px; }
form .field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
```

- [ ] **Step 2: Implement setup.html**

Create `studio_app/static/setup.html`:
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Studio App — First Run</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<main>
  <h1>Set up Studio App</h1>
  <p class="muted">Pick a folder for all data. Put it inside a Google Drive Desktop synced folder for automatic backup.</p>
  <form id="setup-form" class="col">
    <div class="field">
      <label for="data_root">Data root (absolute path)</label>
      <input id="data_root" name="data_root" required placeholder="C:\Users\You\Google Drive\Studio">
    </div>
    <div><button class="primary" type="submit">Initialize</button></div>
    <p id="err" class="muted"></p>
  </form>
</main>
<script src="/static/app.js"></script>
<script>setupSetupForm();</script>
</body></html>
```

- [ ] **Step 3: Implement library.html**

Create `studio_app/static/library.html`:
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Library — Studio App</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<header>
  <strong>Studio App</strong>
  <a class="active" href="/library">Library</a>
  <a href="#" onclick="return false">Schedule</a>
</header>
<main>
  <h1>Library</h1>
  <form id="upload-form" class="row" enctype="multipart/form-data">
    <input id="title" name="title" placeholder="Book title" required>
    <input id="file" name="file" type="file" accept=".pdf,.epub,.docx,.txt" required>
    <button class="primary" type="submit">Add book</button>
    <span id="upload-status" class="muted"></span>
  </form>
  <table id="books-table">
    <thead><tr>
      <th>Title</th><th>Format</th><th>Pages</th><th>Body chars</th><th>Status</th>
    </tr></thead>
    <tbody><tr><td colspan="5" class="muted">Loading…</td></tr></tbody>
  </table>
</main>
<script src="/static/app.js"></script>
<script>setupLibraryPage();</script>
</body></html>
```

- [ ] **Step 4: Implement book.html**

Create `studio_app/static/book.html`:
```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Book — Studio App</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<header>
  <strong>Studio App</strong>
  <a href="/library">← Library</a>
</header>
<main>
  <h1 id="title">Loading…</h1>
  <p class="muted" id="meta"></p>
  <table>
    <tr><th>Format</th><td id="format"></td></tr>
    <tr><th>Pages</th><td id="pages"></td></tr>
    <tr><th>Body chars</th><td id="body_chars"></td></tr>
    <tr><th>Raw chars</th><td id="raw_chars"></td></tr>
    <tr><th>Chars / page</th><td id="cpp"></td></tr>
    <tr><th>Images</th><td id="images"></td></tr>
    <tr><th>Status</th><td id="status"></td></tr>
    <tr><th>Source path</th><td id="source_path" class="muted"></td></tr>
  </table>
</main>
<script src="/static/app.js"></script>
<script>setupBookPage();</script>
</body></html>
```

- [ ] **Step 5: Implement app.js**

Create `studio_app/static/app.js`:
```javascript
async function jsonFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

async function setupSetupForm() {
  const form = document.getElementById('setup-form');
  const err = document.getElementById('err');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    err.textContent = '';
    const data_root = document.getElementById('data_root').value.trim();
    try {
      await jsonFetch('/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data_root }),
      });
      location.href = '/library';
    } catch (e) { err.textContent = e.message; }
  });
}

async function setupLibraryPage() {
  const form = document.getElementById('upload-form');
  const status = document.getElementById('upload-status');
  const tbody = document.querySelector('#books-table tbody');

  async function refresh() {
    const { books } = await jsonFetch('/api/books');
    if (!books.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="muted">No books yet.</td></tr>';
      return;
    }
    tbody.innerHTML = books.map(b => `
      <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
        <td>${escapeHtml(b.title)}</td>
        <td>${b.format}</td>
        <td>${b.pages || '—'}</td>
        <td>${b.body_chars.toLocaleString()}</td>
        <td>${b.status}</td>
      </tr>`).join('');
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    status.textContent = 'Uploading…';
    const fd = new FormData();
    fd.append('title', document.getElementById('title').value);
    fd.append('file', document.getElementById('file').files[0]);
    try {
      const r = await fetch('/api/books', { method: 'POST', body: fd });
      if (!r.ok) throw new Error(await r.text());
      status.textContent = 'Done.';
      form.reset();
      await refresh();
    } catch (e) {
      status.textContent = e.message;
    }
  });

  await refresh();
}

async function setupBookPage() {
  const id = location.pathname.split('/').pop();
  const b = await jsonFetch(`/api/books/${id}`);
  document.getElementById('title').textContent = b.title;
  document.getElementById('meta').textContent = `Slug: ${b.slug}`;
  document.getElementById('format').textContent = b.format;
  document.getElementById('pages').textContent = b.pages || '—';
  document.getElementById('body_chars').textContent = b.body_chars.toLocaleString();
  document.getElementById('raw_chars').textContent = b.raw_chars.toLocaleString();
  document.getElementById('cpp').textContent = b.chars_per_page || '—';
  document.getElementById('images').textContent = b.images;
  document.getElementById('status').textContent = b.status;
  document.getElementById('source_path').textContent = b.source_path;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}
```

- [ ] **Step 6: Add HTML fallback routes to main.py**

Edit `studio_app/main.py`. Add to imports:
```python
from fastapi.responses import FileResponse, RedirectResponse
```

Add inside `build_app` before `return app`:
```python
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    row = conn.execute("SELECT value FROM app_setting WHERE key='data_root'").fetchone()
    if row and row["value"]:
        return RedirectResponse(url="/library")
    return RedirectResponse(url="/setup")

@app.get("/setup", include_in_schema=False)
def setup_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "setup.html")

@app.get("/library", include_in_schema=False)
def library_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "library.html")

@app.get("/books/{book_id}", include_in_schema=False)
def book_page(book_id: int) -> FileResponse:
    return FileResponse(STATIC_DIR / "book.html")
```

- [ ] **Step 7: Add a smoke test for HTML routes**

Append to `tests/test_routes_system.py`:
```python


async def test_root_redirects_to_library_when_configured(client):
    r = await client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/library"


async def test_setup_page_returns_html(client):
    r = await client.get("/setup")
    assert r.status_code == 200
    assert "<form" in r.text
```

- [ ] **Step 8: Run, confirm pass**

```bash
uv run pytest -v
```
Expected: all green (slug 6, db 6, settings 6, parser 3, ingest 5+1skip, system 3, books 5, settings_routes 4 = ~38 passing tests).

- [ ] **Step 9: Manual smoke test**

```bash
uv run studio-app
```
Expected:
1. Console prints `Studio App running at http://127.0.0.1:8765`.
2. Browser opens; if `data_root` not yet set, redirects to `/setup`.
3. Enter an absolute path, click Initialize → redirects to `/library`.
4. Use the Add Book form to upload `tests/fixtures/sample.txt` with title "Sample".
5. Row appears in the table. Click row → book detail shows.
6. Stop the server (Ctrl+C), restart, refresh library — book still there.

- [ ] **Step 10: Commit**

```bash
git add studio_app/static/ studio_app/main.py tests/test_routes_system.py
git commit -m "feat(studio): minimal setup/library/book HTML pages"
```

---

## Phase 1 done-criteria

- [ ] All tests green: `uv run pytest -v`
- [ ] `uv run studio-app` boots, opens browser, first-run wizard works
- [ ] TXT upload ingests, parses, lists in library
- [ ] Restart preserves state (book row + files survive)
- [ ] No code uses `book_analyzer.gui` or other Qt deps — studio_app is web-only
- [ ] No background threads yet — Phase 3
- [ ] No viewer yet — Phase 4
- [ ] No marks, sessions, calendar — later phases

## Self-review pass

Spec coverage for Phase 1:
- §3.1 process model: FastAPI on 127.0.0.1:8765 ✓ (Task 6)
- §3.3 filesystem layout: `data_root/books/<slug>/source/`, `view/`, `metadata.json` ✓ (Task 5)
- §4 schema: full DDL applied ✓ (Task 2)
- §4.1 app_setting keys: defaults seeded via `_DEFAULTS` ✓ (Task 3)
- §6.2 Library tab Books grid: minimal list with add-book form ✓ (Task 9)
- §6.1 Book detail: minimal stats panel ✓ (Task 9)
- §11 parser reuse: parser_adapter imports book_analyzer ✓ (Task 4)
- §13 mutagen choice: not used in Phase 1 (audio scan is Phase 3) — deferred OK

Out of Phase 1 by design: viewer, marks, sessions, schedule, calendar, audio scan, snapshot, exports.

No placeholders, no TBD markers, no "similar to Task N" shortcuts. Function names match across tasks: `slugify`, `connect`, `migrate`, `load`, `save_key`, `is_configured`, `parse_book`, `ingest_book`, `build_app`. JSON payload shapes match between routes and tests.
