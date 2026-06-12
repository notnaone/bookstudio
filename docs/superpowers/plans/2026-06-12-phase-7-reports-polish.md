# Phase 7 — Reports & Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** CSV exports (streamed to browser, optional save to `data_root/exports/`), settings page UI, log rotation, marks.json → DB restore tool, and remaining polish items surfaced across earlier audits. End state: shippable v1. After this phase the studio app does everything in the locked spec.

**Prereqs:** Phase 6 merged. ~165 tests passing.

**6 tasks.**

---

## File structure

**New:**
```
studio_app/exports.py              # CSV builders for books / sessions / audio_files
studio_app/routes/exports.py       # streaming endpoints + cleanup
studio_app/log_setup.py            # rotating file handler config
studio_app/marks_restore.py        # tool: rebuild mark rows from marks.json
studio_app/static/settings.html
studio_app/static/settings.js
tests/test_exports.py
tests/test_routes_exports.py
tests/test_marks_restore.py
```

**Modified:**
```
studio_app/main.py                 # log_setup; settings route
studio_app/routes/system.py        # POST /api/marks/restore endpoint
studio_app/static/library.html     # Settings link in nav
studio_app/static/app.js           # setupSettingsPage
```

---

## Cross-cutting rules

- Streamed CSV: `StreamingResponse(generator, media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=...'})`. No buffering in memory beyond the row generator.
- Optional disk save: when query param `?save=1`, write the same generator output to `data_root/exports/<scope>-<timestamp>.csv` IN ADDITION to streaming.
- All CSV column orders are stable across runs (alphabetical or schema-declared, pick one and document).

---

## Task 0: CSV builders

**Files:** `studio_app/exports.py`, `tests/test_exports.py`

- [ ] Generators that yield CSV rows (header first, then data) for three scopes:
  ```python
  def export_books_csv(conn, *, status=None, from_date=None, to_date=None) -> Iterator[str]
  def export_sessions_csv(conn, *, kind='all', from_date=None, to_date=None) -> Iterator[str]
  def export_audio_files_csv(conn, *, book_id=None) -> Iterator[str]
  ```
- [ ] Books: id, slug, title, publisher_name (JOIN), narrator_name (JOIN), status, pages, body_chars, hours_recorded (from book_stats), progress_pct, planned_end, created_at.
- [ ] Sessions: id, kind ('reading' or 'recording' or 'editing'), book_id, book_title, narrator_id, narrator_name, started_at, ended_at, start_page, end_page, active_seconds (reading only), auto_closed (reading only).
- [ ] Audio files: id, book_id, book_title, filename, duration_seconds, size_bytes, mtime, scanned_at.
- [ ] Use `csv.writer` to a StringIO, yield each row separately so streaming works.
- [ ] Tests: row counts match DB query; CSV is valid (parseable back); date-range filter applies; status filter applies.
- [ ] Commit: `feat(studio): CSV export builders`

---

## Task 1: Streaming export endpoints

**Files:** `studio_app/routes/exports.py`, `tests/test_routes_exports.py`

- [ ] Endpoints:
  - `GET /api/export/books.csv?status=&from=&to=&save=0`
  - `GET /api/export/sessions.csv?kind=&from=&to=&save=0`
  - `GET /api/export/audio_files.csv?book_id=&save=0`
- [ ] Each returns a `StreamingResponse`. If `save=1` AND `data_root/exports/` exists, also write a copy named `<scope>-<utc_iso>.csv`.
- [ ] `POST /api/export/cleanup` body `{older_than_days: int}` — deletes files in `data_root/exports/` older than N days; returns `{deleted: N}`.
- [ ] Tests: streamed response has correct content-type + filename header; save=1 writes file; cleanup respects age.
- [ ] Commit: `feat(studio): streaming CSV export endpoints + cleanup`

---

## Task 2: Settings UI page

**Files:** `studio_app/static/settings.html`, `studio_app/static/settings.js`, `studio_app/main.py` (route)

- [ ] `/settings` route serving settings.html.
- [ ] Form fields:
  - data_root (editable, with warning "Moving data_root requires restart")
  - ics_url_studio_1, ics_url_studio_2 (with "Test connection" button → `POST /api/schedule/refresh` and surface result)
  - pace_unit (dropdown)
  - All five interval seconds (numeric inputs)
- [ ] Save → PATCH /api/settings with only changed fields.
- [ ] Section "Exports cleanup": age input + button → POST /api/export/cleanup.
- [ ] Section "Snapshot now" mirrors the library top-bar button.
- [ ] Section "Restore marks from JSON" → POST /api/marks/restore.
- [ ] Commit: `feat(studio): settings page with editable config + maintenance actions`

---

## Task 3: marks.json → DB restore tool

**Files:** `studio_app/marks_restore.py`, `tests/test_marks_restore.py`, `studio_app/routes/system.py` (endpoint)

- [ ] `restore_marks_from_disk(conn, data_root) -> dict` — walks every `books/<slug>/marks.json`, INSERTs missing mark rows (matched on book_slug + page + coords). Returns `{restored: N, skipped_existing: M, errors: [...]}`.
- [ ] Endpoint: `POST /api/marks/restore` — runs the tool, returns the result.
- [ ] Tests: scratch DB + a marks.json on disk → restore → rows exist.
- [ ] Commit: `feat(studio): marks restoration from JSON sidecar`

---

## Task 4: Log rotation

**Files:** `studio_app/log_setup.py`, `studio_app/main.py`

- [ ] `configure_logging(data_root)` — root logger writes to `data_root/app.log` via `RotatingFileHandler(maxBytes=10*1024*1024, backupCount=3)`. Also keeps a StreamHandler for stderr.
- [ ] Call from `main()` before `build_app()`. Don't call it in tests (conftest can leave logging at defaults).
- [ ] No test (it's wiring); manual smoke verifies file appears.
- [ ] Commit: `feat(studio): rotating app.log under data_root`

---

## Task 5: First-run wizard polish + final UI sweep

**Files:** `studio_app/static/setup.html`, `app.js`, any other small fixes

- [ ] Setup wizard adds optional steps for ICS URLs and a default narrator.
- [ ] Library top bar adds a Settings link.
- [ ] Live viewer adds a small "session id" indicator in the corner (for debugging session reaper).
- [ ] Run the full demo from spec acceptance and fix anything ugly.
- [ ] Commit: `feat(studio): first-run wizard polish + UI sweep`

---

## Phase 7 done-criteria

- [ ] Tests target ~185 passed + 2 skipped.
- [ ] Full demo from the spec works end-to-end without manual SQL:
  1. Fresh checkout → install → run → setup wizard → enter data_root + ICS URLs + create one narrator.
  2. Upload PDF/EPUB/DOCX/TXT books, parse each.
  3. Add publishers, assign each book.
  4. Schedule page shows calendar events; click [Start Session] → viewer opens with active session.
  5. Drag rectangles on pages, add comments → marks survive restart.
  6. Audio scanner picks up MP3s placed in book audio folders; stats reflect chars/h.
  7. Reading-session pace badge shows live + baseline; unit toggle works.
  8. Export books.csv → opens in Excel with correct columns.
  9. Restart with `studio.live.sqlite` deleted → snapshot restore → state intact.
  10. Settings page lets you edit everything.
- [ ] No background thread leaks (visible via `ps`).
- [ ] All UI buttons either work or are removed.

## Self-review

| Spec section | Where |
|---|---|
| §6.2 Export bar | Tasks 0 + 1 + 2 |
| §6 Settings UI | Task 2 |
| §11 Reuse + glue | (already done across phases) |
| §10 Mark restoration | Task 3 |
| §12 app.log rotation | Task 4 |
| §13 mutagen / mammoth / unified viewer / first-run wizard | Locked across Phases 3/4/7 |

---

# Final ship checklist

- [ ] All 7 phase plans archived in `docs/superpowers/plans/`.
- [ ] All 7 phase progress ledgers in `docs/superpowers/progress/`.
- [ ] `master` contains 7 merge commits (`merge: phase N ...`).
- [ ] `README.md` (write it now if missing) explains: install via `uv sync`, run via `uv run studio-app`, first-run setup, where data_root and local_state_dir live, and the backup story.
- [ ] Tag `v1.0.0` on the merge commit of Phase 7.
- [ ] Optional: PyInstaller bundle as `dist/StudioApp.exe`.
