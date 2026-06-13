# BookStudio — Full Codebase Audit Prompt (Opus / Codex)

> **Purpose:** Structured instructions for a senior auditor reviewing the entire `studio_app` after Phases 1–6 on `master`. The auditor must understand product intent, map every screen control to spec behavior, and find bugs that unit tests miss.

---

## 1. Product context

**BookStudio** is a single-user, single-machine FastAPI web app (`127.0.0.1:8765`) for an audiobook recording engineer. It does NOT record audio. It manages:

- Book catalog + ingest (PDF/EPUB/DOCX/TXT via `book_analyzer`)
- Narrators, publishers, assignment history
- Audio folder scanning → pace/progress stats (mutagen)
- Live in-browser viewer with marks, sessions, hotkeys, split view
- Schedule whiteboard (ICS mirror + manual items + JIT onboarding)
- SQLite snapshot to Google Drive-synced `data_root/studio.sqlite`

**Locked artifacts (do not suggest changing):**
- `book_analyzer/` package
- `studio_app/migrations/001_initial.sql`

**Authoritative spec:** `docs/superpowers/specs/2026-06-12-studio-app-design.md`

**Test baseline:** `uv run pytest -q` → 178 passed, 2 skipped

---

## 2. Architecture map (verify implementation matches)

### 2.1 Background daemons (`main.py` lifespan)

| Daemon | Module | Interval setting | Must NOT |
|--------|--------|------------------|----------|
| AudioScanner | `background.py` | `audio_scan_interval_seconds` | Duplicate `audio_file` rows |
| SessionReaper | `reaper.py` | `reaper_interval_seconds` | Close sessions with recent heartbeat |
| CalendarPoller | `calendar_poller.py` | `calendar_poll_interval_seconds` | Touch `resolved_*` or `action_status` on ICS upsert |
| SnapshotJob | `snapshot.py` | `snapshot_interval_seconds` | Write partial `studio.sqlite` (must use `.tmp` + rename) |

All writers should serialize via `db_lock` (`hold()`). Flag any writer that bypasses it.

### 2.2 Data locations

| Path | Role |
|------|------|
| `local_state_dir/studio.live.sqlite` | Live WAL database |
| `data_root/studio.sqlite` | Drive-synced snapshot |
| `local_state_dir/data_root.txt` | Pointer for cold-start recovery |
| `data_root/books/<slug>/source/` | Original upload |
| `data_root/books/<slug>/view/` | Paginated HTML or raw PDF/EPUB |
| `data_root/books/<slug>/marks.json` | Mirror of mark rows |

### 2.3 API surface (verify routes exist and behave per spec §7)

Audit each router under `studio_app/routes/` and `viewer_routes.py`. For every endpoint check: auth N/A (local), validation, error codes, idempotency where spec implies it, `db_lock` usage.

---

## 3. Screen-by-screen UI audit

Read `studio_app/static/*.html` and `app.js` / `live.js` / `schedule.js`. For **each screen**, list every interactive element and verify wired behavior.

### 3.1 `/setup` — First-run wizard

| Element | Expected behavior |
|---------|-------------------|
| `data_root` input | Absolute path; POST `/api/setup` creates folders, seeds `app_setting`, persists `data_root.txt` |
| Initialize button | Redirect to `/library` on success |

### 3.2 `/library` — Library hub

| Element | Expected behavior |
|---------|-------------------|
| Tabs: Books / Narrators / Publishers | Switch panels |
| Books: filter q, status, narrator, publisher | GET `/api/books` with query params |
| Add book form (title + file) | POST `/api/books` multipart ingest |
| Narrators: create name + alias | POST `/api/narrators` |
| Publishers: create name + notes | POST `/api/publishers` |
| Row click | Navigate to book/narrator detail |
| **Snapshot status** | Polls `/api/heartbeat` every 30s; green/yellow/red by age |
| **Snapshot now** | POST `/api/snapshot` |

### 3.3 `/books/:id` — Book detail

| Element | Expected behavior |
|---------|-------------------|
| Title, status, genre, planned end, notes, audio folder | PATCH `/api/books/:id` |
| Narrator / publisher selects | PATCH with FK wiring + `narrator_book` history |
| Draft banner + Confirm setup | Clears `is_draft` only when publisher + genre set |
| Stats panel | From `book_stats` via GET |
| Re-scan audio | POST `/api/books/:id/rescan_audio` |
| **Open in viewer** | Navigate `/live/:id`; warn if draft |

### 3.4 `/narrators/:id` — Narrator detail

| Element | Expected behavior |
|---------|-------------------|
| Name, calendar_alias, notes | PATCH `/api/narrators/:id` |
| Stats | `narrator_stats` |
| Upcoming sessions | `schedule_item` where `resolved_narrator_id` and future start |
| Current work | Books `in_progress` for narrator |
| History | `narrator_book` rows |

### 3.5 `/schedule` — Schedule whiteboard

| Element | Expected behavior |
|---------|-------------------|
| List / Lanes toggle | Two views of same data |
| Refresh calendars | POST `/api/schedule/refresh` |
| Manual add form | POST `/api/schedule` manual row |
| Row / chip click | Detail modal; mirror rows read-only except status |
| **Start Session** | POST `/api/schedule/:id/start_session` → Case A/B/C |
| Case A | Redirect `/live/:book_id?session_id=` (no duplicate session) |
| Case B | Book picker overlay |
| Case C | JIT wizard overlay |

### 3.6 JIT wizard (schedule overlay)

| Element | Expected behavior |
|---------|-------------------|
| Narrator select or create | Multipart POST `/api/schedule/:id/jit` |
| Link future events | Sets `calendar_alias` |
| File dropzone | Ingest with `is_draft=1` |
| Launch | Open live viewer with session |

### 3.7 `/settings` — Minimal settings (Phase 5–6)

| Element | Expected behavior |
|---------|-------------------|
| ICS URL studio 1/2 | PATCH `/api/settings` |
| Sync calendars now | PATCH settings + POST refresh |
| (Phase 7 will expand) | |

### 3.8 `/live/:id` or `/live/:a/:b` — Live viewer

| Element | Expected behavior |
|---------|-------------------|
| Search input | Filter marks; spec says Ctrl+F focus (may be deferred) |
| Viewer page indicator | Adapter `getTotalPages()` / current page |
| Active page counter +/- | PATCH `/api/books/:id/active_page` debounced |
| Pace badge click | Cycle `pace_unit` via PATCH settings |
| Session timer | Heartbeat every 10s; pauses when tab hidden |
| Close session | POST end; reaper is authority |
| `?session_id=` | Resume existing session (no duplicate create) |
| Mark drag / M hotkey | POST marks; mirror to JSON |
| Split view | Two panes, focused border, hotkeys to focused pane |

---

## 4. Domain field semantics (verify correct usage in code)

### 4.1 `book` table highlights

| Field | Meaning |
|-------|---------|
| `current_page` | Engineer-tracked active page (not viewer scroll) |
| `view_path` | Dir for HTML pages OR source file for PDF/EPUB |
| `audio_folder` | Scanned for `audio_file` rows |
| `is_draft` | Incomplete profile; viewer allowed with warning |
| `status` | planned / in_progress / done / archived |

### 4.2 `reading_session`

| Field | Meaning |
|-------|---------|
| `tracked_progress_page` | Engineer counter during session |
| `active_seconds` | Visible-time accumulator via heartbeat |
| `schedule_item_id` | Link when started from schedule |
| `auto_closed` | Set by reaper |

### 4.3 `schedule_item`

| Field | Meaning |
|-------|---------|
| `google_event_id` | ICS UID; NULL for manual |
| `action_status` | pending/started/completed/skipped/cancelled |
| `resolved_*` | Engineer resolution; never overwritten by ICS poll |

---

## 5. Audit methodology

1. **Read spec §6–§11** and roadmap phases 1–6 plans.
2. **Read every Python module** in `studio_app/` end-to-end (not grep-only).
3. **Read all static JS** (`app.js`, `live.js`, `schedule.js`) for race conditions, duplicate API calls, modal stacking bugs.
4. **Trace production wiring** in `main.py` — especially `poll_fn`, `db_lock`, startup order (recovery → migrate → daemons).
5. **Cross-check tests** — note paths covered only by mocks that hide production bugs (Phase 5 F-01 pattern).
6. **Classify findings:** BLOCKER / MAJOR / MINOR / DEFERRED(spec-intentional).
7. **For each finding:** file:line, observed vs expected, reproduction steps, suggested fix, test to add.

---

## 6. Required output format

```markdown
## Executive summary
## Findings table (ID, Severity, Area, One-line summary)
## Detailed findings (F-01…)
## Spec compliance matrix (section → status → gap)
## UI element coverage (screen → element → status)
## Test gap analysis
## Suggested fix order
## Verdict (ship-ready / needs hardening)
```

**Do not** report style nits, missing Phase 7 features, or schema migration ideas.

---

## 7. Known deferred (not bugs unless implemented wrong)

- Phase 7: full settings page, CSV exports, marks.json cold restore, Ctrl+F in live viewer
- F-09 recursive audio folder scan (product sign-off)
- Drive Desktop online detection (impossible)

---

## 8. Files to read (minimum)

```
studio_app/main.py
studio_app/db.py db_lock.py settings.py ingest.py pagination.py
studio_app/audio_scanner.py background.py reaper.py calendar_poller.py ics_client.py
studio_app/snapshot.py recovery.py viewer_routes.py parser_adapter.py slug.py
studio_app/routes/*.py
studio_app/static/app.js live.js schedule.js
studio_app/static/*.html
tests/test_*.py (spot coverage gaps)
docs/superpowers/specs/2026-06-12-studio-app-design.md
```
