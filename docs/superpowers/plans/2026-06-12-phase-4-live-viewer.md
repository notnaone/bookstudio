# Phase 4 — Live Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** The audio engineer can open a book in a custom in-browser viewer with: PDF/EPUB/DOCX/TXT support, an engineer-controlled active-page counter, switchable pace metric, persistent search, rectangle overlay marks with comments, side-by-side split view, hotkey marking, and reading-session timing with heartbeat + server-side reaper. End state: opening a book starts a session row; closing it ends one; marks survive restart; pace shows live and baseline values.

**Architecture:** Server-side DOCX/TXT pagination at import time (DOM-aware, per spec §11). One shared `LiveViewer` JS shell on `/live/<book_id>` (and `/live/<a>/<b>` for split). Adapters: PDF.js, epub.js, static HTML pages. Reading sessions have a `last_heartbeat_at` and an `auto_closed` flag; a `SessionReaper` daemon closes stale ones. Marks CRUD goes through `/api/marks`; a JSON mirror is written to `data_root/books/<slug>/marks.json` on every change.

**Tech Stack:** Adds `mammoth` (DOCX → HTML), `httpx` (already declared). Frontend uses PDF.js + epub.js loaded from CDN. No bundler.

**Prereqs:** Phase 3 merged. Schema has all needed fields (no migration).

This is the largest phase. **12 tasks.**

---

## File structure

**New:**
```
studio_app/pagination.py           # docx/txt → page-NNNN.html
studio_app/viewer_routes.py        # serves view/page-NNNN.html with proper headers
studio_app/routes/marks.py         # CRUD for mark rows + marks.json mirror
studio_app/routes/sessions.py      # reading_session lifecycle
studio_app/reaper.py               # SessionReaper daemon
studio_app/static/live.html        # viewer shell
studio_app/static/live.js          # viewer + adapter logic
studio_app/static/live.css         # viewer-specific styles
tests/test_pagination.py
tests/test_routes_marks.py
tests/test_routes_sessions.py
tests/test_reaper.py
tests/fixtures/tiny.docx           # tiny DOCX
tests/fixtures/tiny.epub           # tiny EPUB
```

**Modified:**
```
studio_app/ingest.py               # call pagination for docx/txt; set view_path to view/ dir
studio_app/main.py                 # start SessionReaper; mount marks + sessions routers; /live route
studio_app/routes/system.py        # heartbeat reports reaper.last_run_at
studio_app/static/book.html        # "Open in viewer" button
studio_app/static/app.js           # button wires to /live/<id>
studio_app/routes/books.py         # PATCH active_page endpoint
```

---

## Cross-cutting rules

- Pagination is DOM-aware. Never slice raw HTML strings.
- Mark coordinates are percentages (`x_pct`, `y_pct`, `w_pct`, `h_pct`) so zoom-safe.
- Hotkeys (`]`, `[`, `M`, etc.) are no-ops when focus is in `INPUT`/`TEXTAREA`/`SELECT`/contenteditable.
- `tracked_progress_page` is the engineer-incremented "active page", separate from viewer scroll.
- `beforeunload` is best-effort. The reaper is the authority on session closure.

---

## Task 0: DOCX + EPUB fixtures

- [ ] Create `tests/fixtures/_generate_docx.py` using `python-docx` to write `tiny.docx` (3 paragraphs, ~150 chars).
- [ ] Create `tests/fixtures/_generate_epub.py` using `ebooklib` to write `tiny.epub` with one chapter.
- [ ] Run both, commit fixtures + generators.
- [ ] Commit `test: tiny DOCX + EPUB fixtures for viewer tests`

---

## Task 1: `studio_app/pagination.py` — DOM-aware paginator

**Files:** `studio_app/pagination.py`, `tests/test_pagination.py`

- [ ] Failing tests: pagination of TXT into N pages; DOCX→HTML→pagination preserves DOM; no `<p>` tag is split across pages; pages emit valid HTML.

```python
def paginate_html_to_pages(
    html: str, chars_per_page: int, *, page_template: str | None = None
) -> list[str]:
    """Split `html` into pages, breaking only at closed top-level element ends.

    Returns list of standalone HTML page strings. Each page is wrapped in
    a fixed-aspect-ratio container via `page_template` (or a default).
    """
```

- [ ] Implementation: parse with `bs4`, iterate top-level children, track running text-length, emit a page when crossing threshold AND current child is a closed structural element (`p`, `h1-h6`, `li`, `blockquote`, `div`).
- [ ] Also expose `paginate_txt(text, chars_per_page) -> list[str]`: wraps blank-line-separated paragraphs in `<p>` and delegates to the HTML paginator.
- [ ] DOCX path: `mammoth.convert_to_html(...)` → paginator.
- [ ] Test cases:
  - `paginate_txt("para1\n\npara2", chars_per_page=500)` returns 1 page containing both paragraphs.
  - Long TXT with 6 paragraphs at low char threshold yields multiple pages, none with a half-split paragraph.
  - DOCX with 3 `<p>` returns expected structure.
- [ ] Commit: `feat(studio): DOM-aware paginator for DOCX/TXT`

---

## Task 2: ingest.py wires pagination

**Files:** `studio_app/ingest.py`, `tests/test_ingest.py`

- [ ] For `format in ('docx', 'txt')`, after parsing, run the paginator and write `view/page-0001.html` … `view/page-NNNN.html`.
- [ ] Set `book.view_path` to the `view/` directory path (changes contract — previously was the source file).
- [ ] Test: ingest a DOCX → `view_path` is a dir, contains at least one `page-*.html`.
- [ ] Don't paginate PDF (view_path = source path) or EPUB (view_path = source path; epub.js handles native).
- [ ] Commit: `feat(studio): ingest paginates DOCX/TXT to view/page-NNNN.html`

---

## Task 3: `studio_app/viewer_routes.py` — serve pages

**Files:** `studio_app/viewer_routes.py`, `tests/test_viewer_routes.py`

- [ ] `GET /api/books/{book_id}/view/page-{n}.html` → FileResponse from `view_path/page-{n:04d}.html`. 404 if file missing.
- [ ] `GET /api/books/{book_id}/view/source` → FileResponse with `source_path` (for PDF.js and epub.js to load the raw file).
- [ ] Mount in main.py.
- [ ] Tests: 200 with content-type; 404 for nonexistent page.
- [ ] Commit: `feat(studio): viewer file-serving routes`

---

## Task 4: Marks CRUD + JSON mirror

**Files:** `studio_app/routes/marks.py`, `tests/test_routes_marks.py`

- [ ] Endpoints:
  - `GET /api/books/:book_id/marks` → list, ordered by `page, created_at`.
  - `POST /api/marks` → body `{book_id, page, x_pct, y_pct, w_pct, h_pct, color?, comment?}`. Validates 0 ≤ pct ≤ 100.
  - `PATCH /api/marks/:id` → updates color/comment only.
  - `DELETE /api/marks/:id`.
- [ ] After every write: rewrite `<data_root>/books/<slug>/marks.json` atomically (temp+rename) with the current full mark list for that book.
- [ ] Tests: create, list, patch comment, delete, JSON mirror present and accurate after each.
- [ ] Reject coordinates outside [0,100] with 400.
- [ ] Commit: `feat(studio): marks CRUD with marks.json mirror`

---

## Task 5: Reading sessions API

**Files:** `studio_app/routes/sessions.py`, `tests/test_routes_sessions.py`

- [ ] Endpoints:
  - `POST /api/reading_session` → body `{book_id, schedule_item_id?}`. Inserts row with `started_at=now`, `start_page=book.current_page`, `tracked_progress_page=start_page`, `last_heartbeat_at=now`, `ended_at=NULL`. Sets narrator_id from book.
  - `PATCH /api/reading_session/:id/heartbeat` → body `{tracked_progress_page, active_seconds_delta}`. Updates session and `book.current_page`. Returns 409 if session already ended (so a stale tab sees the reaper closed it).
  - `POST /api/reading_session/:id/end` → body `{end_page?, active_seconds?}`. Sets `ended_at=now`.
- [ ] Tests: full lifecycle; heartbeat advances book.current_page; reaper-closed session returns 409 on heartbeat; end is idempotent.
- [ ] Commit: `feat(studio): reading_session lifecycle endpoints + heartbeat`

---

## Task 6: Session reaper daemon

**Files:** `studio_app/reaper.py`, `tests/test_reaper.py`

- [ ] `SessionReaper(conn, idle_timeout_seconds, interval_seconds)` — same daemon pattern as `AudioScanner`. Every `interval_seconds`, runs:
  ```sql
  UPDATE reading_session
     SET ended_at = last_heartbeat_at,
         end_page = tracked_progress_page,
         auto_closed = 1
   WHERE ended_at IS NULL
     AND (last_heartbeat_at IS NULL
          OR last_heartbeat_at < datetime('now', ?, ...))
  ```
- [ ] Test: insert open session with old `last_heartbeat_at`, run reaper iteration, confirm row has `ended_at` and `auto_closed=1`.
- [ ] Wire into main.py with `interval=60`, `idle_timeout=300` (from settings).
- [ ] heartbeat endpoint reports `last_reaper_run_at`.
- [ ] Commit: `feat(studio): session reaper daemon thread`

---

## Task 7: PATCH `/api/books/:id/active_page`

**Files:** `studio_app/routes/books.py`, `tests/test_routes_books.py`

- [ ] Endpoint: `PATCH /api/books/:id/active_page` body `{tracked_progress_page}`. Validates 1 ≤ n ≤ book.pages (or any if pages=0). Updates `book.current_page`. Returns updated row.
- [ ] Why a separate endpoint: the live viewer hammers this on every active-page advance; we don't need the full PATCH machinery.
- [ ] Tests: success, 404, bad value 400.
- [ ] Commit: `feat(studio): PATCH /api/books/:id/active_page for live viewer`

---

## Task 8: Live viewer HTML shell

**Files:** `studio_app/static/live.html`, `studio_app/static/live.css`, `studio_app/main.py`

- [ ] Add routes `/live/{book_id}` and `/live/{a}/{b}` serving `live.html`.
- [ ] `live.html` structure:
  - Top bar per pane: search input, viewer page indicator, active-page counter with `−`/`+`, pace badge (clickable unit toggle), session timer, close button.
  - Side rail per pane: marks list.
  - Main area: viewer wrapper that hosts one of the three adapters.
  - Single-pane and split-pane variants determined by URL param parsing in JS.
- [ ] `live.css`: fixed aspect ratio for the page container; absolute-positioned mark divs; focused-pane border accent.
- [ ] Commit: `feat(studio): live viewer HTML shell`

---

## Task 9: Live viewer JS — adapters

**Files:** `studio_app/static/live.js`

- [ ] Import PDF.js + epub.js from CDN at top of `live.html`.
- [ ] Common adapter interface:
  ```js
  interface ViewerAdapter {
    init(container, book): Promise<void>;
    goToPage(n): Promise<void>;
    getTotalPages(): number;
    search(query): Promise<void>;          // highlights matches
    getCurrentViewerPage(): number;        // for the viewer-page indicator
  }
  ```
- [ ] Three implementations: `PdfAdapter`, `EpubAdapter`, `HtmlPagesAdapter` (fetches `/api/books/:id/view/page-N.html` into an iframe).
- [ ] Adapter factory: switch on `book.format`.
- [ ] Commit: `feat(studio): viewer adapters (PDF / EPUB / HTML)`

---

## Task 10: Live viewer JS — session, marks, hotkeys

**Files:** `studio_app/static/live.js` (append)

- [ ] On load: `POST /api/reading_session` for each book. Store session id. Set up heartbeat interval (10 s).
- [ ] Active page counter: `]` advances, `[` rewinds. `PageDown` mirrors `]`. Hotkey context guard:
  ```js
  function shouldIgnoreHotkey(e) {
    const t = e.target;
    return ['INPUT','TEXTAREA','SELECT'].includes(t.tagName) || t.isContentEditable;
  }
  ```
- [ ] On advance: PATCH `/api/books/:id/active_page` (debounced 500ms), and bumped value sent in next heartbeat.
- [ ] Active timer: `document.visibilityState !== 'hidden'` accumulates; sent as `active_seconds_delta` in heartbeat.
- [ ] Marks:
  - Drag in page container: rectangle preview, on mouseup show modal for color/comment → POST `/api/marks`.
  - Hotkey `M` on focused pane: instant mark at current viewer line/paragraph (compute coords from selection or fall back to a small centered rectangle).
  - Marks rendered as absolute-positioned divs over page container.
  - Click rail entry → adapter.goToPage(n), flash mark.
- [ ] Pace badge: live = `(tracked_progress_page - start_page) / (active_seconds / 3600)` in current unit. Baseline = `book.stats.chars_per_hour` → narrator avg → `—`. Returns `—` when pages == 0 or active_seconds < 60.
- [ ] Pace unit toggle: cycles through `chars_per_hour`, `pages_per_hour`, `words_per_hour`, `sec_per_100_pages`. Persisted to `app_setting.pace_unit` via PATCH /api/settings.
- [ ] Close button + `beforeunload`: POST `/api/reading_session/:id/end`.
- [ ] On heartbeat 409: toast "Session was auto-closed after inactivity. Continue as new?" → POST new session at last tracked page.
- [ ] Split view: parse URL `/live/a/b`, mount two adapter instances in side-by-side panes, focused pane (last-clicked) gets accent border + receives hotkeys.
- [ ] Commit: `feat(studio): viewer session lifecycle, marks, hotkeys, split view`

---

## Task 11: Wire "Open in viewer" button on book detail

**Files:** `studio_app/static/book.html`, `studio_app/static/app.js`

- [ ] Add button to book detail page header.
- [ ] On click: `location.href = '/live/' + bookId`.
- [ ] If book is `is_draft=1`: warn before opening (banner already there; just add a confirm dialog).
- [ ] Commit: `feat(studio): open in viewer button on book detail`

---

## Phase 4 done-criteria

- [ ] All tests green: target ~135 passed + 2 skipped (add ~36 new tests).
- [ ] Demo:
  1. Upload a DOCX + a PDF.
  2. Open PDF in `/live/<id>` — PDF renders, active page counter at 1, can advance with `]`.
  3. Drag rectangle on a page → comment modal → save → mark appears + survives reload.
  4. Open second book in `/live/<a>/<b>` — split view, focus border tracks click.
  5. Walk away 6 minutes. Return. Tab gets 409 toast, "Continue" creates a fresh session at last page.
  6. Pace badge shows `—` initially; advance several active pages → live pace appears; toggle unit → display updates.

## Self-review

| Spec section | Where |
|---|---|
| §6.6 Live screen layout + behavior | Tasks 8–11 |
| §6.6 Hotkey context guard | Task 10 |
| §6.6 Active vs viewer page split | Tasks 7 + 10 |
| §6.6 Split view + focused pane | Task 10 |
| §6.6 Marks (drag + M hotkey) | Tasks 4 + 10 |
| §6.6 Session lifecycle + heartbeat + 409 | Tasks 5 + 10 |
| §6.6 Reaper authority | Task 6 |
| §11 DOM-aware pagination | Tasks 1 + 2 |
| §11 Unified shell + adapters | Tasks 8 + 9 |
| §8 Pace formulas + null guards | Task 10 |

**Deferred to Phase 5:**
- JIT onboarding wizard launching live view directly (Phase 5 wires the calendar Start-Session flow).
- Reading-session link to schedule_item.

**Deferred to Phase 6:**
- marks.json restored on cold start if DB lost.
