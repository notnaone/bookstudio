# Phase 5 — Schedule & Calendar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Read-only mirror of two Google Calendar feeds (Studio 1 + Studio 2) as a "whiteboard" view, plus manual schedule items, plus the Just-In-Time onboarding wizard that resolves an unconfigured calendar event into a live session in under 10 seconds.

**Architecture:** ICS feed URLs in `app_setting`. A `CalendarPoller` daemon (~5 min interval) fetches and upserts `schedule_item` rows keyed by `google_event_id`. The Schedule UI shows two lanes (plus an optional Manual lane). Clicking [Start Session] resolves the narrator via longest-alias-prefix match: Case A launches viewer directly, B prompts for book pick, C opens the JIT wizard inline.

**Tech Stack:** Adds `icalendar` (pure Python ICS parser). `httpx` already declared.

**Prereqs:** Phase 4 merged. Live viewer accepts `schedule_item_id` query param on session start.

**8 tasks.**

---

## File structure

**New:**
```
studio_app/ics_client.py             # fetch + parse ICS
studio_app/calendar_poller.py        # background daemon
studio_app/routes/schedule.py        # schedule_item CRUD + sync + start-session
studio_app/static/schedule.html
studio_app/static/schedule.js
studio_app/static/jit_wizard.html    # inline overlay fragment
tests/test_ics_client.py
tests/test_calendar_poller.py
tests/test_routes_schedule.py
tests/fixtures/sample.ics
```

**Modified:**
```
studio_app/main.py                   # CalendarPoller start; /schedule route
studio_app/routes/settings_routes.py # already accepts ics_url_studio_1/2; verify wiring
studio_app/routes/system.py          # heartbeat reports last_calendar_sync_at
studio_app/static/library.html       # "Schedule" nav link wires to /schedule
```

---

## Cross-cutting rules

- The poller NEVER touches `resolved_narrator_id`, `resolved_book_id`, `resolved_at`, or `action_status`. Calendar is truth ONLY for `start_time`, `end_time`, `raw_title`, `notes`.
- Disappeared events are not deleted — set `action_status='cancelled'` so any `reading_session.schedule_item_id` references stay valid.
- Narrator alias matching is **longest-prefix wins** (spec §9.3):
  ```sql
  SELECT id FROM narrator
  WHERE LOWER(?) LIKE LOWER(calendar_alias) || '%'
  ORDER BY LENGTH(calendar_alias) DESC
  LIMIT 1;
  ```

---

## Task 0: ICS fixture + ics_client

**Files:** `studio_app/ics_client.py`, `tests/test_ics_client.py`, `tests/fixtures/sample.ics`

- [ ] Create `sample.ics` with 3 VEVENTs (different UIDs, distinct titles like "Chris - Foo", "Christina - Bar", "Booking").
- [ ] Implement:
  ```python
  def parse_ics(ics_bytes: bytes) -> list[CalendarEvent]:
      """Parse ICS bytes into a list of CalendarEvent(uid, summary, description,
         dtstart, dtend) using icalendar.Calendar.from_ical."""
  def fetch_ics(url: str, *, timeout=30) -> bytes:
      """GET the URL via httpx; return body bytes. Raises on non-2xx."""
  ```
- [ ] Tests: parse the fixture → 3 events with correct fields. Timezones normalized to UTC.
- [ ] Commit: `feat(studio): ICS client (parse + fetch)`

---

## Task 1: schedule_item CRUD (manual)

**Files:** `studio_app/routes/schedule.py`, `tests/test_routes_schedule.py`

- [ ] Endpoints:
  - `GET /api/schedule?from=&to=&source=` — filter by date range + source.
  - `POST /api/schedule` — manual rows only (source='manual', kind required ∈ {recording, editing, deadline}).
  - `PATCH /api/schedule/:id` — change `action_status`, resolved_*, notes. Refuse to modify `raw_title`/`start_time`/`end_time` on calendar-mirror rows (`google_event_id IS NOT NULL`).
  - `DELETE /api/schedule/:id` — manual rows only. Calendar-mirror rows can only be cancelled.
- [ ] Mount in main.py.
- [ ] Tests cover all paths + the "can't edit mirror" guard.
- [ ] Commit: `feat(studio): schedule_item CRUD with manual/mirror enforcement`

---

## Task 2: CalendarPoller daemon

**Files:** `studio_app/calendar_poller.py`, `tests/test_calendar_poller.py`

- [ ] `CalendarPoller(conn, interval_seconds, fetch_fn, urls_provider)`:
  - `urls_provider(conn)` → `{'studio_1': url1 or None, 'studio_2': url2 or None}`.
  - On each iteration: for each non-None URL → `fetch_fn(url)` → parse → upsert into `schedule_item` keyed on `(google_event_id)`. Set `source` to 'studio_1'/'studio_2'. Set `last_synced_at=now`.
  - Mark `action_status='cancelled'` for rows whose `google_event_id` is no longer in the latest pull from the same source.
  - `last_sync_at` instance attribute.
- [ ] Tests: monkeypatched fetch returns the sample fixture; first iter inserts 3 rows; remove 1 from the fixture and re-iter — that row becomes `action_status='cancelled'`; manual rows untouched.
- [ ] Commit: `feat(studio): CalendarPoller background daemon`

---

## Task 3: Wire poller + heartbeat

**Files:** `studio_app/main.py`, `studio_app/routes/system.py`

- [ ] In main(): construct `CalendarPoller(conn, interval=app_setting.calendar_poll_interval_seconds, fetch_fn=fetch_ics, urls_provider=lambda c: ...)` and `.start()`.
- [ ] heartbeat: `last_calendar_sync_at: poller.last_sync_at if poller else None`.
- [ ] Test: heartbeat key present.
- [ ] Commit: `feat(studio): wire CalendarPoller into main(); heartbeat reports it`

---

## Task 4: Narrator alias resolution helper

**Files:** `studio_app/routes/schedule.py` (append), `tests/test_routes_schedule.py` (append)

- [ ] Helper `resolve_narrator_from_title(conn, raw_title) -> int | None` implementing longest-prefix-wins SQL.
- [ ] Endpoint `POST /api/schedule/:id/start_session`:
  - 404 if schedule_item missing.
  - Resolve narrator. If narrator has exactly one `in_progress` book assigned → "case A": insert `reading_session` (start_page = book.current_page), set `schedule_item.resolved_narrator_id`, `resolved_book_id`, `action_status='started'`. Return `{session_id, book_id, mode: 'A'}`.
  - If narrator has multiple `in_progress` books → "case B": return `{mode: 'B', narrator_id, candidate_books: [...]}` and don't start a session.
  - If no narrator match → "case C": return `{mode: 'C', raw_title}`. Client opens JIT wizard.
- [ ] Tests for A/B/C and the Chris-vs-Christina case.
- [ ] Commit: `feat(studio): start-session resolution with longest-alias-wins matching`

---

## Task 5: JIT onboarding endpoint

**Files:** `studio_app/routes/schedule.py` (append), tests

- [ ] `POST /api/schedule/:id/jit` — body `{narrator_name, calendar_alias?, save_alias?, title, audio_folder?}` + multipart `file` (book upload).
  - Tricky: this endpoint must accept both JSON-like params AND a file upload. Use `Form()` for the text fields and `UploadFile` for the file (same pattern as `/api/books`).
  - Find or create narrator (if `save_alias` is true, set `calendar_alias`).
  - Ingest the book with `is_draft=1`.
  - Assign narrator to book (insert narrator_book row).
  - Insert `reading_session` linked to the schedule_item.
  - Set `schedule_item.action_status='started'`, `resolved_*`.
  - Return `{session_id, book_id, narrator_id}`.
- [ ] Tests for: existing narrator, new narrator with alias save, alias collision → 400, file-format reject → 400.
- [ ] Commit: `feat(studio): JIT onboarding endpoint`

---

## Task 6: Schedule UI — lanes + start-session button

**Files:** `studio_app/static/schedule.html`, `studio_app/static/schedule.js`, main.py route

- [ ] `/schedule` route serving `schedule.html`.
- [ ] List view (default): table by date with columns `source | start | end | title | resolved | status | actions`.
- [ ] Lanes view toggle: three columns (Studio 1, Studio 2, Manual). Today highlighted at top.
- [ ] Each row has [Start Session] button:
  - JS POSTs `/api/schedule/:id/start_session`.
  - Case A response → `location.href = '/live/' + book_id` (the session was created server-side, viewer will continue).
  - Case B → small overlay with candidate book picker, then `POST .../start_session` with `?book_id=chosen` (or do a PATCH to set resolved_book_id then re-fire start_session).
  - Case C → open `jit_wizard.html` overlay.
- [ ] Manual row creation form (separate from calendar mirror rows).
- [ ] Commit: `feat(studio): schedule page with lanes + start-session flow`

---

## Task 7: JIT wizard overlay

**Files:** `studio_app/static/jit_wizard.html`, `studio_app/static/schedule.js` (append), styling

- [ ] Inline overlay form (no route change). Three sections per spec §6.5:
  1. Narrator: existing dropdown OR "+ Create New" with name field + "Link future events" checkbox (sets `calendar_alias`).
  2. Book: title (prefilled), file dropzone, audio folder path.
  3. Launch button: POSTs to `/api/schedule/:id/jit` (multipart), then `location.href = '/live/' + book_id`.
- [ ] Show transient toast/banner if parser is still running (parser is sync in current ingest; if we want async, defer to Phase 7).
- [ ] Commit: `feat(studio): JIT onboarding wizard overlay`

---

## Phase 5 done-criteria

- [ ] Tests target ~155 passed + 2 skipped.
- [ ] Demo:
  1. Paste two private iCal URLs into Settings → wait for next sync.
  2. Schedule page shows events from both calendars.
  3. Click [Start Session] on an event whose title prefix matches an existing narrator with 1 in_progress book → viewer opens with session active.
  4. Add a narrator with alias "Chris" + another with "Christina" → click event titled "Christina - Foo" → resolves to Christina (longest wins).
  5. Click event with unmapped name → JIT wizard appears; fill it out; viewer opens immediately.
  6. Add a manual deadline row → appears in the list with kind=deadline.

## Self-review

| Spec section | Where |
|---|---|
| §6.4 Schedule lanes | Task 6 |
| §6.4 Start-session A/B/C | Tasks 4 + 6 |
| §6.5 JIT wizard | Tasks 5 + 7 |
| §9 ICS over OAuth | Tasks 0–3 |
| §9.3 Longest-alias-wins | Task 4 |
| §9.4 Why ICS not API | (documented in spec; code matches) |

**Deferred to Phase 7:**
- Schedule export (CSV).
- Reschedule via drag-drop in lanes view.
