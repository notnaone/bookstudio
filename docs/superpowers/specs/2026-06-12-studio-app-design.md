# Audiobook Studio App — Design Spec

**Date:** 2026-06-12
**Status:** Draft, awaiting user approval
**Source:** Brainstorming session from spreadsheet at `Untitled spreadsheet.xlsx`

---

## 1. Purpose

A local web application for managing an audiobook recording studio. Wraps the existing `book_analyzer` parser into a five-screen workflow that tracks books, narrators, schedules, and live recording sessions. Single-user, single-machine, with Google Drive Desktop providing automatic file-level backup and Google Calendar (via ICS) providing a read-only "whiteboard" view of studio bookings.

The engineer (single operator) uses this app at their console while a narrator records in Adobe Audition. The app never touches audio recording itself; it manages the metadata, the source-text viewer with annotations, and the progress / pacing analytics derived from audio files on disk.

---

## 2. Scope & Non-Goals

### In scope (v1)

- Five screens: Book detail, Library/Reports, Narrator detail, Schedule, Live recording view.
- Book ingest from PDF, EPUB, DOCX, TXT via the existing parser.
- Per-book audio folder scanning to derive recording time, pace, progress.
- Custom in-browser book viewer with frozen page layout and rectangle overlay annotations.
- Live reading sessions: timer, engineer-controlled active-page counter, switchable pace metric, rapid hotkey marking.
- Read-only Google Calendar integration via private ICS feeds for two studios.
- Just-In-Time onboarding wizard launched from any unresolved calendar event.
- CSV export streamed directly to browser.
- SQLite database snapshotted every 5 minutes into a Drive-synced folder.

### Out of scope (explicit non-goals)

- No multi-user / authentication. Single engineer, single machine.
- No Google Drive API. Google Drive Desktop daemon handles uploads.
- No Google Calendar API or write-back. ICS read-only forever.
- No audio recording, editing, waveform display, or DAW integration.
- No mobile / responsive layout. Studio monitor (≥1080p) only.
- No real-time collaboration, websockets, or push.
- No email / SMS notifications.
- No PDF reports. CSV only.
- No automatic OCR for image-only PDFs.
- No telemetry, auto-update, or cross-platform packaging.

---

## 3. Architecture

### 3.1 Process model

- One Python process running **FastAPI** on `127.0.0.1:8765`.
- Engineer opens `http://localhost:8765` in any modern browser (Chrome/Edge tested).
- Background threads inside the same process:
  - **Audio scanner** — every 5 min and on-demand. Walks each `book.audio_folder`, upserts `audio_file` rows, recomputes `book_stats` / `narrator_stats`.
  - **Calendar poller** — every 5 min. Fetches each configured ICS URL, upserts `schedule_item` rows by `google_event_id`.
  - **Session reaper** — every 60 s. Closes any `reading_session` with `ended_at IS NULL` whose `last_heartbeat_at` is older than 5 min, with `auto_closed=1`.
  - **Snapshot job** — every 5 min. Checkpoints WAL, copies live DB to the Drive-synced folder as an atomic snapshot.
- All four background jobs serialize their writes through a single `asyncio.Lock`. UI reads never block.

### 3.2 Frontend stack

- Vanilla JavaScript (ES modules), no bundler.
- `htmx` for form interactions if hand-rolled JS gets tedious — optional.
- **PDF.js** for PDF rendering.
- **epub.js** for EPUB rendering (synthetic-page mode for stable pagination).
- DOCX and TXT are pre-paginated server-side at import via a DOM-aware paginator (see Section 11); rendered as a sequence of static HTML files inside a fixed-aspect-ratio container that scales via CSS transform rather than reflow.
- Overlay marks are absolute-positioned `<div>`s on a page wrapper, with coordinates stored as percentages so zoom and resize preserve their position.

### 3.3 Filesystem layout

```
<data_root>/                       ← inside a Google Drive Desktop synced folder
├── studio.sqlite                  ← canonical DB snapshot (rewritten every 5 min)
├── books/
│   └── <book_slug>/
│       ├── source/                ← original publisher file (untouched)
│       ├── view/                  ← normalized viewable form:
│       │                              PDF: kept as-is
│       │                              EPUB: kept as-is
│       │                              DOCX: converted to page-0001.html … page-NNNN.html via mammoth
│       │                              TXT: paginated to page-0001.html … page-NNNN.html
│       ├── metadata.json          ← output of book_analyzer parser
│       └── marks.json             ← mirror of mark rows for this book, atomic-written on every change
├── exports/                       ← (only when "Save to data_root" checkbox is on at export time)
└── app.log

<local_state>/                     ← NOT synced; e.g. %APPDATA%\StudioApp\
├── studio.live.sqlite             ← live DB the app actually writes to
├── studio.live.sqlite-wal
└── studio.live.sqlite-shm
```

The app reads/writes the **live** SQLite file. The snapshot job uses SQLite's online backup API to write an atomic copy to `<data_root>/studio.sqlite`. On startup: if `live` is missing but a snapshot exists, restore it.

Audio folders are not inside `data_root`. They live wherever the engineer already keeps them; absolute paths are stored in `book.audio_folder`. The engineer is responsible for arranging that those folders are also in a Drive-synced location if they want audio backed up.

---

## 4. Data Model

SQLite, WAL mode, `synchronous=NORMAL`, `wal_autocheckpoint=1000`.

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
  calendar_alias TEXT UNIQUE,           -- nullable; matches first-name string in calendar titles
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Book
CREATE TABLE book (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  publisher_id INTEGER,                  -- nullable to allow JIT draft
  source_path TEXT NOT NULL,
  view_path TEXT NOT NULL,
  format TEXT NOT NULL,                  -- pdf | epub | docx | txt
  genre TEXT,
  publisher_notes TEXT,
  body_chars INTEGER DEFAULT 0,
  raw_chars INTEGER DEFAULT 0,
  chars_per_page INTEGER DEFAULT 0,
  pages INTEGER DEFAULT 0,
  images INTEGER DEFAULT 0,
  charts_tables INTEGER DEFAULT 0,
  audio_folder TEXT,                     -- absolute path
  drive_sync_path TEXT,                  -- informational label only, not used for upload
  narrator_id INTEGER,
  planned_end DATE,
  current_page INTEGER DEFAULT 1,        -- last reached active page persisted across sessions
  status TEXT CHECK(status IN ('planned','in_progress','done','archived')) DEFAULT 'planned',
  is_draft INTEGER DEFAULT 0,            -- 1 = created via JIT wizard, needs follow-up review
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

-- 5. Reading session = book viewer open → close
CREATE TABLE reading_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,                   -- nullable: book may have no narrator yet
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,                   -- NULL = active
  start_page INTEGER NOT NULL,
  end_page   INTEGER,
  tracked_progress_page INTEGER,         -- engineer-incremented active page
  active_seconds INTEGER DEFAULT 0,
  last_heartbeat_at DATETIME,
  auto_closed INTEGER DEFAULT 0,         -- 1 = reaper closed it
  schedule_item_id INTEGER,              -- if launched from a schedule click
  FOREIGN KEY (book_id)          REFERENCES book(id),
  FOREIGN KEY (narrator_id)      REFERENCES narrator(id),
  FOREIGN KEY (schedule_item_id) REFERENCES schedule_item(id)
);

-- 6. Work session = manually logged recording or editing in DAW
CREATE TABLE work_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,                   -- nullable
  kind TEXT CHECK(kind IN ('recording','editing')) NOT NULL,
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,
  start_page INTEGER,
  end_page   INTEGER,
  notes TEXT,
  FOREIGN KEY (book_id)     REFERENCES book(id),
  FOREIGN KEY (narrator_id) REFERENCES narrator(id)
);

-- 7. Audio files discovered in book.audio_folder
CREATE TABLE audio_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id         INTEGER NOT NULL,
  work_session_id INTEGER,               -- optional correlation by mtime window
  path     TEXT NOT NULL,
  filename TEXT NOT NULL,
  duration_seconds REAL DEFAULT 0,
  size_bytes INTEGER DEFAULT 0,
  mtime DATETIME,
  scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id)         REFERENCES book(id),
  FOREIGN KEY (work_session_id) REFERENCES work_session(id)
);

-- 8. Schedule (calendar mirror + manual rows)
CREATE TABLE schedule_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT CHECK(source IN ('studio_1','studio_2','manual')) NOT NULL,
  google_event_id TEXT UNIQUE,           -- NULL for manual rows
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
  kind TEXT CHECK(kind IN ('recording','editing','deadline')),  -- manual rows only
  last_synced_at DATETIME,
  FOREIGN KEY (resolved_narrator_id) REFERENCES narrator(id),
  FOREIGN KEY (resolved_book_id)     REFERENCES book(id)
);

-- 9. Rectangle overlay marks on book pages
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

-- 10. Derived analytics (recomputed; safe to drop and rebuild)
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
```

### 4.1 Required `app_setting` keys (seeded on first run)

| key | purpose |
|---|---|
| `data_root` | absolute path to the synced data root |
| `local_state_dir` | absolute path to the unsynced live DB location |
| `ics_url_studio_1` | private iCal URL for Studio 1 calendar |
| `ics_url_studio_2` | private iCal URL for Studio 2 calendar |
| `pace_unit` | one of: `chars_per_hour` \| `pages_per_hour` \| `words_per_hour` \| `sec_per_100_pages` |
| `snapshot_interval_seconds` | default 300 |
| `audio_scan_interval_seconds` | default 300 |
| `calendar_poll_interval_seconds` | default 300 |
| `reaper_interval_seconds` | default 60 |
| `session_idle_timeout_seconds` | default 300 |

---

## 5. Sync & Backup

### 5.1 Snapshot mechanism

Every `snapshot_interval_seconds` (default 5 min) and on graceful shutdown:

1. `PRAGMA wal_checkpoint(TRUNCATE)` on the live DB.
2. Open SQLite online-backup connection from `<local_state>/studio.live.sqlite` to `<data_root>/studio.sqlite.tmp`.
3. Atomic rename `studio.sqlite.tmp` → `studio.sqlite`.

Drive Desktop sees a fully-written file flip, never a torn write.

### 5.2 Marks JSON redundancy

Every `mark` insert/update/delete also rewrites `<data_root>/books/<slug>/marks.json` via temp-file + rename. Plain-text backup of annotations independent of the DB.

### 5.3 Sync status UI

Top bar shows: `Last snapshot: 2 min ago · [Snapshot now]`. The app cannot directly observe Drive Desktop's upload state — that's surfaced by Drive Desktop's own tray icon.

### 5.4 Cold-start recovery

On launch, if `<local_state>/studio.live.sqlite` is missing or zero bytes and `<data_root>/studio.sqlite` exists, copy snapshot → live and continue. If both are missing, run schema migration on a fresh DB.

---

## 6. Screens

### 6.1 Book (detail) — `/books/<id>`

- **Header:** title, format pill, status dropdown, publisher + narrator links, planned end date picker. Banner "Incomplete draft profile" when `is_draft=1`, with "Confirm setup" button that requires `publisher_id` and `genre` before clearing the flag.
- **Stats panel** (read-only, from `book_stats`): pages, body chars, hours recorded, progress %, chars/h, pages/h. "Re-scan audio" button.
- **Files panel:** source path, view path, audio folder picker, optional `drive_sync_path` label, marks.json path. "Re-run parser" button.
- **Sessions panel:** combined chronological list of `reading_session` and `work_session` rows. Click expands details.
- **Open in viewer** → opens Live screen for this book.

### 6.2 Library / Reports — `/library`

Three tabs: Books · Narrators · Publishers.

- **Books tab:** sortable table (title, narrator, status, progress %, planned end, hours recorded). Filter row at top. "Add book" button opens upload flow (drop file → app copies to `data_root/books/<slug>/source/` → parser runs → row created).
- **Narrators tab:** list, click → narrator detail.
- **Publishers tab:** inline-editable name and notes.
- **Export bar:** scope picker (books / sessions / audio files), optional date range and filter. "Download CSV" streams `Content-Type: text/csv` to browser. Optional "Also save to data_root/exports/" checkbox. "Clean up exports older than N days" button.

### 6.3 Narrator (detail) — `/narrators/<id>`

- Header: name, notes (editable), `calendar_alias` input.
- Stats card from `narrator_stats`.
- **Current work:** books with `status='in_progress'` assigned to this narrator + progress %.
- **History:** `narrator_book` rows.
- **Upcoming sessions:** `schedule_item` rows where `resolved_narrator_id = this` and `start_time > now`.
- **Assign book** action: pick unassigned book → updates `book.narrator_id` and inserts `narrator_book` row.

### 6.4 Schedule — `/schedule`

Toggle in top-right: **List ↔ Calendar**.

- **Lanes:** two side-by-side columns (Studio 1, Studio 2) plus an optional Manual lane. Today highlighted, scrolls forward.
- **List view:** sortable table, columns: date, source, kind, raw_title, resolved book, resolved narrator, action_status.
- **Calendar view:** month grid, chips colored by `source`; chip click opens edit modal (manual rows editable, calendar-mirrored rows read-only except `action_status`).
- **Start Session button** on each row:
  - **Case A — known link:** narrator `calendar_alias` resolves to exactly one narrator with exactly one `in_progress` book → launch Live view, insert `reading_session` with `schedule_item_id` set, set `schedule_item.action_status='started'`.
  - **Case B — ambiguous:** narrator resolves but has multiple `in_progress` books → drop-down to pick book → launch.
  - **Case C — unconfigured:** alias unmapped → open JIT wizard inline overlay.
- **Manual row creation:** "Add manual schedule item" form for kinds `recording`/`editing`/`deadline`, no `google_event_id`.

### 6.5 JIT onboarding wizard

Inline overlay launched from Case C above. Three sections:

1. **Narrator** — select existing or `[+ Create New]`. New narrator: name pre-filled from calendar string, `calendar_alias` auto-set if "Link future events" checkbox is on.
2. **Book ingest** — title pre-filled, file dropzone (PDF/EPUB/DOCX/TXT), audio folder path.
3. **Launch** — inserts `book` with `is_draft=1`, copies source file, kicks off parser in background thread, immediately opens Live view with placeholder stats.

Stats panel back-fills when parser completes. Engineer clears `is_draft` later from book detail screen.

### 6.6 Live (rec session) — `/live/<book_id>` or `/live/<book1>/<book2>`

**Layout:** one viewer pane, or two side-by-side when split.

**Per-pane top bar:**
- Search input (always visible; `Ctrl+F` focuses it).
- Viewer page indicator: `current viewer page / total`.
- **Active page counter:** `Active: 47 / 312` with `−` / `+` buttons.
- Pace badge (switchable: chars/h · pages/h · words/h · sec/100p). Baseline shown next to live.
- Session timer.
- "Close session" button.

**Per-pane side rail:** marks list for the current book, click → jump + flash.

**Behavior:**
- On open: insert `reading_session` with `start_page = book.current_page`, `tracked_progress_page = book.current_page`, `ended_at = NULL`.
- Viewer scroll / page-turn updates the viewer's display only. **Does not change** `tracked_progress_page`.
- Engineer advances active page via hotkey `]` (rewind `[`), or the `+`/`−` buttons. Update `book.current_page` and `reading_session.tracked_progress_page` (debounced 500 ms).
- `PageDown` is a secondary binding for `]`.
- Heartbeat every 10 s: `PATCH /api/reading_session/<id>/heartbeat` with `{tracked_progress_page, active_seconds_delta}`.
- Active timer pauses when `document.visibilityState === 'hidden'`.
- Live pace = `(tracked_progress_page − start_page) / (active_seconds / 3600)`, displayed in current `pace_unit`.
- Baseline pace fallback: `book_stats.chars_per_hour` → `narrator_stats.avg_chars_per_hour` → `—`.

**Marks:**
- Drag = rectangle overlay. Modal asks color + optional comment.
- Hotkey `M` = instant mark on the currently active line/paragraph with default color. Transient comment input pops; `Enter` saves, `Esc` keeps blank.
- All marks stored as percentages relative to the page wrapper.

**Hotkey context guard.** All viewer hotkeys (`]`, `[`, `M`, `Ctrl+F`, etc.) are filtered by event target. When focus is inside an `INPUT`, `TEXTAREA`, `SELECT`, or `contenteditable` element (search box, comment input, notes field), the global handler is a no-op:

```js
document.addEventListener('keydown', (e) => {
  const t = e.target;
  if (['INPUT','TEXTAREA','SELECT'].includes(t.tagName) || t.isContentEditable) return;
  // hotkey dispatch
});
```

**Split view:**
- Two `reading_session` rows active concurrently, independent timers and active-page counters.
- Focused pane has a distinct colored border. All hotkeys route to focused pane only.
- Closing one pane ends only that session.

**On close:**
- `beforeunload` best-effort: `POST /api/reading_session/<id>/end`.
- Authoritative close handled by reaper if heartbeat lapses > 5 min.

---

## 7. API Surface

```
# Books
GET    /api/books
POST   /api/books                       multipart: file + {title, publisher_id?, audio_folder?}
GET    /api/books/:id
PATCH  /api/books/:id
PATCH  /api/books/:id/active_page       {tracked_progress_page}
POST   /api/books/:id/reparse
POST   /api/books/:id/rescan_audio
GET    /api/books/:id/marks
GET    /api/books/:id/view/page-:n.html  static-served paginated HTML for DOCX/TXT

# Narrators
GET    /api/narrators
POST   /api/narrators                   {name, calendar_alias?, notes?}
GET    /api/narrators/:id
PATCH  /api/narrators/:id

# Publishers
GET    /api/publishers
POST   /api/publishers
PATCH  /api/publishers/:id

# Reading sessions
POST   /api/reading_session             {book_id, schedule_item_id?}
PATCH  /api/reading_session/:id/heartbeat   {tracked_progress_page, active_seconds_delta}
POST   /api/reading_session/:id/end     {end_page, active_seconds}

# Work sessions (manual recording/editing logs)
POST   /api/work_session
PATCH  /api/work_session/:id
DELETE /api/work_session/:id

# Marks
POST   /api/marks                       {book_id, page, x_pct,y_pct,w_pct,h_pct, color?, comment?}
PATCH  /api/marks/:id
DELETE /api/marks/:id

# Schedule
GET    /api/schedule                    ?from=&to=&source=
POST   /api/schedule                    manual rows only
PATCH  /api/schedule/:id                action_status, kind, notes, resolved_*
POST   /api/schedule/refresh            force ICS poll
POST   /api/schedule/:id/start_session  Case A/B helper: insert reading_session + return its id

# Exports
GET    /api/export/books.csv            streams; optional ?save=1 also writes to data_root/exports
GET    /api/export/sessions.csv
GET    /api/export/audio_files.csv
POST   /api/export/cleanup              {older_than_days}

# System
GET    /api/heartbeat                   {active_sessions, last_snapshot_at, last_calendar_sync_at}
POST   /api/snapshot                    force snapshot
GET    /api/settings
PATCH  /api/settings
```

---

## 8. Pacing Calculation Rules

**Live pace (current session):**
```
seconds = reading_session.active_seconds
pages   = tracked_progress_page - start_page
chars   = pages * book.chars_per_page   (approximation)
```
Returns `null` if `seconds < 60` (avoid divide-by-tiny) **or** if `pages == 0` (engineer has not yet advanced the active page). The UI renders `null` as `—` to avoid a `0 pph` value flickering on session open.

**Book-level baseline:**
```
book_stats.total_audio_seconds = sum(audio_file.duration_seconds for this book)
book_stats.chars_per_hour = book.body_chars * 3600 / total_audio_seconds
book_stats.pages_per_hour = book.pages * 3600 / total_audio_seconds
book_stats.progress_pct   = current_page / pages
```

**Narrator-level baseline:**
```
narrator_stats.total_audio_seconds = sum across all this narrator's books
narrator_stats.avg_chars_per_hour  = weighted average over books with audio
narrator_stats.avg_pages_per_hour  = weighted average over books with audio
```

**Fallback chain for the Live view baseline display:**
`book.chars_per_hour` (if total_audio_seconds > 0) → `narrator.avg_chars_per_hour` → `—`.

**Pace unit:** UI-selectable, persisted in `app_setting.pace_unit`. All four units computable from the same underlying chars/sec rate.

---

## 9. Calendar Integration (ICS)

### 9.1 Configuration

Engineer pastes each calendar's "Secret address in iCal format" into Settings → Studio 1 URL, Studio 2 URL. Stored in `app_setting`.

### 9.2 Poll loop

Every `calendar_poll_interval_seconds`:

1. `GET` the ICS URL with `httpx` (timeout 30 s, retry-with-backoff up to 1 hr).
2. Parse with `icalendar` library.
3. For each `VEVENT`, upsert into `schedule_item` matched on `google_event_id = UID`:
   - Update `start_time`, `end_time`, `raw_title` (= `SUMMARY`), `notes` (= `DESCRIPTION`), `last_synced_at`.
   - Never touch `resolved_narrator_id`, `resolved_book_id`, `resolved_at`, `action_status`.
4. For events present in DB but not in the latest ICS pull, set `action_status='cancelled'` (do not delete — preserves any `reading_session.schedule_item_id` references).

### 9.3 Resolution at click time

On `[Start Session]` click:

```
narrator_match = lookup narrator by calendar_alias matched as case-insensitive
                 prefix of raw_title (e.g. "Chris" matches "Chris - SciFi Project")
case A: narrator_match found AND it has exactly one in_progress book
        → resolved_narrator_id, resolved_book_id, action_status='started'
        → open Live view with reading_session.schedule_item_id set
case B: narrator_match found AND multiple in_progress books
        → present book picker
case C: no narrator_match
        → open JIT wizard
```

**Longest-alias-wins rule (the "Chris vs Christina" trap).** When two aliases both prefix the title (e.g. `"Chris"` and `"Christina"` on `"Christina - Session 1"`), the longer alias must win. The lookup query:

```sql
SELECT id FROM narrator
WHERE LOWER(?) LIKE LOWER(calendar_alias) || '%'
ORDER BY LENGTH(calendar_alias) DESC
LIMIT 1;
```

### 9.4 Why ICS, not the Google Calendar API

- Zero OAuth, zero Google Cloud project, zero token refresh.
- One-time config (paste URL).
- Sufficient lag tolerance (typical Google ICS refresh is 5–15 min; whiteboard does not need real-time).
- Trivial to mock and test offline.

Acknowledged tradeoff: 10–20 min visibility delay from a calendar edit to the app.

---

## 10. Failure Modes

| Failure | Response |
|---|---|
| Parser fails on import | Book created with `is_draft=1`, stats stay zero, banner offers re-run. Live view still works on raw file. |
| Audio folder empty | Pace falls back to narrator avg → `—`. No error. |
| Audio folder missing on disk | Yellow warning chip on book screen. Scan job skips silently. |
| Drive Desktop daemon offline | App can't detect directly. Sync indicator only reflects local snapshot freshness. |
| ICS feed unreachable | Schedule shows stale chip after 30 min. Retries with backoff. Last-known events still visible. |
| Reaper closes an active session | Tab's next heartbeat gets 409. UI toasts and offers to start a new session at the last tracked page. |
| Split-view pane crashes | Sibling pane continues. Orphan reaped independently. |
| Disk full | Transaction rolls back. Banner. App continues read-only. |
| `data_root` path moved | Settings screen forces re-pick before any write. |
| Same alias on two narrators | Prevented by UNIQUE constraint at insert. |
| Mark coordinates out of range | Not rendered; surfaced in a "stale marks" list with delete buttons. |

---

## 11. Reuse of Existing `book_analyzer`

The existing CLI is imported as a Python module by the FastAPI app. The `parse` command logic becomes a function call; output flows into the DB instead of stdout JSON. The CLI binary stays available for offline batch use. No changes to parser internals.

Pagination work for DOCX/TXT is a thin new module on top of the parser: take its per-page char counts and emit `view/page-NNNN.html`.

**Pagination must be DOM-aware, not string-sliced.** Mammoth produces clean HTML paragraphs. The paginator walks the resulting DOM, accumulates visible text length across element boundaries, and emits a page break **only at closed structural element boundaries** (`</p>`, `</h1>`, `</li>`, etc.) once the running char count crosses `chars_per_page`. Hard slicing on raw HTML strings is forbidden — it cuts tags and entities, breaks the DOM, and corrupts the viewer.

TXT files are first wrapped into one `<p>` per source paragraph (split on blank lines) before the same DOM-aware paginator runs.

---

## 12. Operational Notes

- App runs as `python -m studio_app` (or pyinstaller bundle later).
- Logs to `<data_root>/app.log` with rotation at 10 MB.
- No migrations framework in v1; schema version stored in `app_setting.schema_version`, manual SQL files in `migrations/`.
- Browser launch: app prints `http://localhost:8765` and opens the default browser via `webbrowser.open()` on startup.

---

## 13. Resolved implementation choices

- **Audio metadata: `mutagen`.** Pure Python, fast duration reads, no ffmpeg dependency. `pydub` rejected — its ffmpeg requirement adds deployment friction with no benefit for read-only duration scans.
- **DOCX → HTML: `mammoth`.** Outputs semantic `<p>`/`<h1>`/`<li>` structure that the DOM-aware paginator (Section 11) consumes directly. `pandoc` rejected — multi-megabyte external CLI, overkill for this pipeline.
- **Viewer architecture: unified shell + format adapters.** A single `LiveViewer` shell renders the top bar (search, active page counter, pace badge, timer, close) and the marks rail. Inside its content frame, one of three adapters is mounted based on `book.format`:
  - `PdfAdapter` → PDF.js
  - `EpubAdapter` → epub.js in synthetic-page mode
  - `HtmlPagesAdapter` → updates an `<iframe>` `src` to `/api/books/:id/view/page-:n.html`
  All three adapters implement a common interface: `goToPage(n)`, `getTotalPages()`, `search(query)`, `getViewportPageMetrics()`. The shell only ever talks to the interface.
- **Settings UI: first-run wizard + a settings link.** First launch detects no `data_root` setting and runs a wizard (pick data_root, optional ICS URLs, optional default narrator). Subsequent edits via Settings link in nav.

---

**End of design spec.**
