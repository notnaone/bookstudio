# Phase 5 — Schedule & Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Read-only mirror of two Google Calendar feeds (Studio 1 + Studio 2) as a whiteboard view, plus manual schedule items, plus the Just-In-Time onboarding wizard that resolves an unconfigured calendar event into a live session in under 10 seconds.

**Architecture:** ICS feed URLs in `app_setting`. A `CalendarPoller` daemon (default 5 min) fetches and upserts `schedule_item` rows keyed by `google_event_id`. The Schedule UI shows list + lane views. `[Start Session]` resolves the narrator via longest-alias-prefix match: Case A launches viewer with an existing session, Case B prompts for book pick, Case C opens the JIT wizard inline.

**Tech Stack:** Adds `icalendar` (pure Python ICS parser). `httpx` already in dev group — promote or add to main deps for poller runtime.

**Prereqs:** Phase 4 merged on `master` (132 passed + 2 skipped). `reading_session.schedule_item_id` column exists; `POST /api/reading_session` already accepts optional `schedule_item_id`.

**9 implementation tasks + audit.**

---

## File structure

**New:**
```
studio_app/ics_client.py             # fetch + parse ICS
studio_app/calendar_poller.py        # background daemon (mirror AudioScanner pattern)
studio_app/routes/schedule.py        # schedule CRUD + sync + start-session + JIT
studio_app/static/schedule.html
studio_app/static/schedule.js
studio_app/static/settings.html      # minimal: ICS URLs + sync now (full page in Phase 7)
studio_app/static/settings.js
tests/test_ics_client.py
tests/test_calendar_poller.py
tests/test_routes_schedule.py
tests/fixtures/sample.ics
```

**Modified:**
```
pyproject.toml                       # icalendar dependency
studio_app/main.py                   # CalendarPoller start/stop; /schedule + /settings routes
studio_app/routes/system.py          # heartbeat.last_calendar_sync_at
studio_app/routes/narrators.py       # upcoming schedule_item rows in GET
studio_app/routes/sessions.py        # GET /api/reading_session/:id (resume from schedule)
studio_app/static/library.html       # Schedule + Settings nav links
studio_app/static/narrator.html      # Upcoming sessions table
studio_app/static/app.js             # setupSettingsPage, narrator upcoming, schedule nav
studio_app/static/live.js            # resume session via ?session_id= query param
```

---

## Cross-cutting rules

- Poller NEVER touches `resolved_narrator_id`, `resolved_book_id`, `resolved_at`, or `action_status`. Calendar is truth only for `start_time`, `end_time`, `raw_title`, `notes`, `last_synced_at`.
- Disappeared events are not deleted — set `action_status='cancelled'` so `reading_session.schedule_item_id` references stay valid.
- Narrator alias matching is **longest-prefix wins** (spec §9.3):
  ```sql
  SELECT id FROM narrator
  WHERE calendar_alias IS NOT NULL
    AND LOWER(?) LIKE LOWER(calendar_alias) || '%'
  ORDER BY LENGTH(calendar_alias) DESC
  LIMIT 1;
  ```
- All poller/ICS tests use monkeypatched `fetch_fn` — never hit real Google URLs in CI.
- `CalendarPoller` uses `db_lock` via `hold()` like scanner and reaper.
- Schedule-created sessions must not be duplicated when the viewer opens — pass `?session_id=` in the redirect URL.

---

## Task 0: ICS fixture + ics_client

**Files:** `pyproject.toml`, `studio_app/ics_client.py`, `tests/test_ics_client.py`, `tests/fixtures/sample.ics`

- [ ] Add `icalendar>=6.0` to `pyproject.toml`; `uv lock`.
- [ ] Create `sample.ics` with 3 `VEVENT`s (distinct UIDs). Titles must include alias traps, e.g. `"Chris - Foo"`, `"Christina - Bar"`, `"Studio booking"`.
- [ ] Implement:
  ```python
  @dataclass(frozen=True)
  class CalendarEvent:
      uid: str
      summary: str
      description: str | None
      dtstart: datetime  # timezone-aware UTC
      dtend: datetime

  def parse_ics(ics_bytes: bytes) -> list[CalendarEvent]:
      """Parse ICS bytes via icalendar.Calendar.from_ical."""

  def fetch_ics(url: str, *, timeout: float = 30.0) -> bytes:
      """GET via httpx; raise on non-2xx."""
  ```
- [ ] Tests: fixture → 3 events with correct UIDs/titles; `dtstart`/`dtend` normalized to UTC.
- [ ] Commit: `feat(studio): ICS client (parse + fetch)`

---

## Task 1: schedule_item CRUD (manual + list)

**Files:** `studio_app/routes/schedule.py`, `tests/test_routes_schedule.py`, `studio_app/main.py` (mount)

- [ ] `GET /api/schedule?from=&to=&source=` — ISO date/datetime filters on `start_time`; optional `source` ∈ `studio_1|studio_2|manual`. Include resolved book/narrator titles via JOIN for display.
- [ ] `POST /api/schedule` — manual rows only:
  ```json
  {"source":"manual","kind":"recording|editing|deadline","start_time":"...","end_time":"...","raw_title":"...","notes":null}
  ```
  Reject if `google_event_id` sent. `kind` required for manual.
- [ ] `PATCH /api/schedule/:id` — allow `action_status`, `kind`, `notes`, `resolved_narrator_id`, `resolved_book_id` (set `resolved_at=now` when either resolved field changes). Refuse changes to `raw_title`, `start_time`, `end_time`, `source`, `google_event_id` when `google_event_id IS NOT NULL`.
- [ ] `DELETE /api/schedule/:id` — manual rows only; 403/409 for calendar-mirror rows.
- [ ] Serialize rows with all fields the UI needs.
- [ ] Tests: CRUD happy paths; mirror-row edit guard; date-range filter.
- [ ] Commit: `feat(studio): schedule_item CRUD with manual/mirror enforcement`

---

## Task 2: CalendarPoller daemon

**Files:** `studio_app/calendar_poller.py`, `tests/test_calendar_poller.py`

- [ ] `sync_calendar_source(conn, source: str, events: list[CalendarEvent]) -> None`:
  - Upsert by `google_event_id` (UID). On insert: `action_status='pending'`, `kind=NULL`.
  - On update: only `start_time`, `end_time`, `raw_title`, `notes`, `last_synced_at`.
  - After processing pull: rows with same `source` + non-null `google_event_id` whose UID not in pull → `action_status='cancelled'`.
  - Manual rows (`source='manual'`) never touched.
- [ ] `CalendarPoller(conn, interval_seconds, fetch_fn, urls_provider, sync_fn, db_lock)` — daemon thread matching `AudioScanner` lifecycle; `last_sync_at: str | None`.
- [ ] Tests with monkeypatched fetch:
  1. First iter → 3 rows inserted (`studio_1`).
  2. Second fixture drops one UID → that row `cancelled`; others unchanged.
  3. Manual row present → still present after sync.
- [ ] Commit: `feat(studio): CalendarPoller background daemon`

---

## Task 3: Wire poller, force refresh, minimal settings UI

**Files:** `studio_app/main.py`, `studio_app/routes/schedule.py`, `studio_app/routes/system.py`, `studio_app/static/settings.html`, `studio_app/static/settings.js`, `studio_app/static/library.html`, `studio_app/static/app.js`

- [ ] Construct `CalendarPoller` in `main()` with locked `fetch_fn` + `sync_fn`; start/stop in lifespan alongside scanner/reaper.
- [ ] `POST /api/schedule/refresh` — run one poll iteration immediately (for demo + settings "Sync now" button); return `{synced_at, items_upserted}`.
- [ ] `GET /api/heartbeat` → `last_calendar_sync_at` from poller.
- [ ] Minimal `/settings` page (Phase 7 expands): fields `ics_url_studio_1`, `ics_url_studio_2`, button "Sync calendars now" → `PATCH /api/settings` then `POST /api/schedule/refresh`.
- [ ] Library header: wire `Schedule` → `/schedule`, add `Settings` → `/settings`.
- [ ] Tests: heartbeat key; refresh endpoint triggers sync (monkeypatch).
- [ ] Commit: `feat(studio): wire CalendarPoller; settings ICS URLs; schedule refresh`

---

## Task 4: Start-session resolution + viewer session resume

**Files:** `studio_app/routes/schedule.py`, `studio_app/routes/sessions.py`, `studio_app/static/live.js`, `tests/test_routes_schedule.py`, `tests/test_routes_sessions.py`

- [ ] `resolve_narrator_from_title(conn, raw_title) -> int | None` — longest-alias-wins SQL.
- [ ] `POST /api/schedule/:id/start_session` — optional JSON `{book_id?: int}` for Case B after picker.
  - **Case A:** narrator resolved + exactly one `book.status='in_progress'` for that narrator (or explicit `book_id` when only one candidate) → insert `reading_session` with `schedule_item_id`, set `resolved_*`, `action_status='started'`. Return `{mode:'A', session_id, book_id}`.
  - **Case B:** narrator resolved + multiple in-progress books and no `book_id` → `{mode:'B', narrator_id, candidate_books:[{id,title},...]}`.
  - **Case C:** no narrator → `{mode:'C', raw_title}`.
  - Re-fire with `book_id` after Case B → Case A path.
- [ ] `GET /api/reading_session/:id` — return open session row; 404 if missing; include `book_id`, `start_page`, `tracked_progress_page`, `active_seconds`, `ended_at`.
- [ ] `live.js`: if URL has `?session_id=N`, call GET instead of POST create; 409 on heartbeat still handled as today.
- [ ] Schedule redirect (Task 6) uses `/live/{book_id}?session_id={id}`.
- [ ] Tests: Chris vs Christina title resolves Christina; A/B/C paths; GET session; live resume integration test optional (JS covered by manual demo).
- [ ] Commit: `feat(studio): start-session resolution; resume existing session in live viewer`

---

## Task 5: JIT onboarding endpoint

**Files:** `studio_app/routes/schedule.py`, `tests/test_routes_schedule.py`

- [ ] `POST /api/schedule/:id/jit` — `multipart/form-data`:
  - Form: `narrator_id` (existing) OR `narrator_name` (create), `calendar_alias`, `link_future_events` (bool), `title`, `audio_folder` (optional).
  - File: `file` (book source).
- [ ] Flow:
  1. Find/create narrator; if `link_future_events`, set `calendar_alias` (400 on UNIQUE collision).
  2. `ingest_book(...)` with `is_draft=1`.
  3. Set `book.narrator_id`, insert `narrator_book`.
  4. Insert `reading_session` with `schedule_item_id`.
  5. Update `schedule_item` `resolved_*`, `action_status='started'`.
  6. Return `{session_id, book_id, narrator_id}`.
- [ ] Tests: new narrator + alias; existing narrator; alias collision → 400; bad file → 400.
- [ ] Commit: `feat(studio): JIT onboarding endpoint`

---

## Task 6: Schedule UI — list, lanes, start-session

**Files:** `studio_app/static/schedule.html`, `studio_app/static/schedule.js`, `studio_app/main.py`

- [ ] `GET /schedule` → `schedule.html`.
- [ ] Toggle **List ↔ Lanes** (spec §6.4).
- [ ] **List view:** sortable table — date, source, kind, title, resolved book/narrator, `action_status`, actions.
- [ ] **Lanes view:** three columns (Studio 1, Studio 2, Manual); today highlighted; chips colored by `source`.
- [ ] Row click → detail modal: calendar-mirror rows read-only except `action_status`; manual rows fully editable via PATCH.
- [ ] `[Start Session]` → POST `start_session`:
  - A → `location.href = '/live/' + book_id + '?session_id=' + session_id`
  - B → overlay book picker → re-POST with `book_id`
  - C → open JIT wizard (Task 7)
- [ ] "Add manual schedule item" form → POST `/api/schedule`.
- [ ] "Refresh calendars" button → POST `/api/schedule/refresh`.
- [ ] Commit: `feat(studio): schedule page with lanes + start-session flow`

---

## Task 7: JIT wizard overlay

**Files:** `studio_app/static/schedule.js`, `studio_app/static/schedule.html` (overlay markup), styles

- [ ] Inline overlay (no route change). Three sections per spec §6.5:
  1. **Narrator** — dropdown of existing narrators OR "+ Create New" with name prefilled from `raw_title` + "Link future events" checkbox.
  2. **Book** — title prefilled, file dropzone, optional audio folder path.
  3. **Launch** — POST `/api/schedule/:id/jit` (multipart) → redirect `/live/{book_id}?session_id={id}`.
- [ ] Close/cancel returns to schedule without navigation.
- [ ] Commit: `feat(studio): JIT onboarding wizard overlay`

---

## Task 8: Narrator upcoming sessions

**Files:** `studio_app/routes/narrators.py`, `studio_app/static/narrator.html`, `studio_app/static/app.js`, `tests/test_routes_narrators.py` (or schedule tests)

- [ ] `GET /api/narrators/:id` includes `upcoming_sessions`: `schedule_item` rows where `resolved_narrator_id = id` AND `start_time > now()` ORDER BY `start_time`.
- [ ] Narrator detail page: table with date, source, title, action_status; link to `/schedule` optional.
- [ ] Test: seed schedule row → appears in narrator GET.
- [ ] Commit: `feat(studio): narrator upcoming sessions from schedule`

---

## Phase 5 done-criteria

- [ ] All tests green: target **~155 passed + 2 skipped** (~23 new tests).
- [ ] Demo:
  1. Open Settings → paste two private iCal URLs (or use `sample.ics` served locally in dev) → Sync now.
  2. Schedule page shows events from both studios + manual lane.
  3. Narrator with alias + one in-progress book → Start Session on matching event → live viewer opens **without duplicate session** (heartbeat uses same `session_id`).
  4. Aliases "Chris" and "Christina" → event "Christina - Foo" resolves to Christina.
  5. Unmapped event → JIT wizard → upload → live viewer opens with draft book banner.
  6. Add manual deadline row → appears with `kind=deadline`.
  7. Narrator detail shows upcoming sessions for that narrator.

## Self-review

| Spec section | Where |
|---|---|
| §6.3 Narrator upcoming sessions | Task 8 |
| §6.4 Schedule list + lanes + start A/B/C | Tasks 4 + 6 |
| §6.5 JIT wizard | Tasks 5 + 7 |
| §9 ICS poll loop | Tasks 0–3 |
| §9.3 Longest-alias-wins | Task 4 |
| §7 `POST /api/schedule/refresh` | Task 3 |
| §7 Settings ICS URLs | Task 3 (minimal UI; Phase 7 full settings) |

**Deferred to Phase 6:** snapshot / sync status (unchanged).

**Deferred to Phase 7:** full settings page, schedule CSV export, calendar drag-reschedule.

**Known gap (acceptable):** ICS retry-with-backoff up to 1 hr (spec §9.2) — implement simple try/except + log in Task 2; exponential backoff can harden in audit if time permits.
