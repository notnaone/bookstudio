# BookStudio — Full Codebase Audit Report

**Date:** 2026-06-12  
**Branch:** `cursor/full-codebase-audit-d61a`  
**Base:** `master` @ Phase 6 (178 passed, 2 skipped)  
**Post-fix baseline:** 184 passed, 2 skipped

---

## Pipeline

| Stage | Agent | Output |
|-------|-------|--------|
| 1. Audit prompt | Composer | `docs/superpowers/audits/2026-06-12-full-codebase-audit-prompt.md` |
| 2. Primary audit | Opus 4.7 | 19 findings (F-01–F-19) |
| 3. Validation | Codex (gpt-5.3-codex-high) | 10 confirmed, 7 partial, 1 rejected, 1 deferred |
| 4. Fix implementation | Composer | This branch |
| 5. Re-audit | Opus 4.7 | See §6 below |

---

## Primary findings (Opus) + Codex validation

| ID | Sev | Summary | Codex | Action |
|----|-----|---------|-------|--------|
| F-01 | BLOCKER | `paginate_txt` does not HTML-escape — XSS/broken DOM | CONFIRMED | **Fixed** — `html.escape()` on paragraph text |
| F-02 | BLOCKER | `start_session` can duplicate open session when `/api/reading_session` exists | CONFIRMED | **Fixed** — cross-path dedupe by `book_id` + schedule idempotency in sessions route |
| F-03 | MAJOR | `POST /api/books` ingest bypasses `db_lock` | PARTIAL | **Fixed** — wrapped `ingest_book` in `hold()` |
| F-04 | MAJOR | Marks CRUD bypasses `db_lock` | PARTIAL | **Fixed** — all mark writes under `hold()` |
| F-05 | MAJOR | Narrators/publishers writes bypass `db_lock` | PARTIAL | **Fixed** — create/patch under `hold()` |
| F-06 | MAJOR | Schedule CRUD bypasses `db_lock` | PARTIAL | **Fixed** — create/patch/delete under `hold()` |
| F-07 | MAJOR | `SnapshotJob` bypasses `db_lock` | PARTIAL | **Fixed** — optional `db_lock` on `SnapshotJob.run_once()` |
| F-08 | MAJOR | `start_session` ignores `resolved_*` fields | CONFIRMED | **Fixed** — honor `resolved_book_id` / `resolved_narrator_id` |
| F-09 | MAJOR | `continueNewSession()` reuses dead `?session_id=` | CONFIRMED | **Fixed** — clear URL param; ended/mismatched sessions create new |
| F-10 | MAJOR | Split view binds both panes to same `session_id` | CONFIRMED | **Fixed** — resume URL session only when `book_id` matches pane |
| F-11 | MAJOR | Case A doesn't promote book to `in_progress` | REJECTED | **Skipped** — Case A only selects `in_progress` books |
| F-12 | MINOR | `active_page` patch missing upper bound in some paths | PARTIAL | Already bounded in `patch_active_page` |
| F-13 | MINOR | ICS timezone parsing edge cases | CONFIRMED | Deferred — low risk for current fixtures |
| F-14 | MINOR | Partial ICS poll failure handling | CONFIRMED | Deferred — poller logs and continues |
| F-15 | MAJOR | Settings PATCH accepts invalid values | CONFIRMED | **Fixed** — validate `pace_unit` + positive int intervals |
| F-16 | MINOR | Narrator history ordering | PARTIAL | No change — acceptable |
| F-17 | MINOR | Heartbeat delta lost on 409 | CONFIRMED | **Fixed** — only subtract delta after successful heartbeat |
| F-18 | MINOR | Schedule notes field UX | CONFIRMED | Deferred — Phase 7 polish |
| F-19 | DEFERRED | Phase 7 book detail items | DEFERRED | Phase 7 scope |

---

## Fixes applied (detail)

### F-01 — TXT HTML escape (`studio_app/pagination.py`)
Paragraph text is escaped before wrapping in `<p>` tags. Prevents script injection and broken markup when ingesting plain-text books containing angle brackets.

### F-02 — Session deduplication (`schedule.py`, `sessions.py`)
- `_open_session_for_book()` checks for open sessions by `book_id` before insert in `_start_case_a`.
- `POST /api/reading_session` also checks open session by `schedule_item_id` when provided.
- Schedule start reuses existing open session and marks schedule item as started.

### F-03–F-07 — `db_lock` coverage
All identified writer paths now acquire `hold(db_lock)`:
- Books ingest, marks CRUD, narrators/publishers CRUD, schedule CRUD
- Settings PATCH and setup POST
- Session end
- SnapshotJob (wired from `main.py`)

### F-08 — Resolved schedule fields (`schedule.py`)
When `resolved_book_id` is set on a schedule item, `start_session` uses it directly instead of re-parsing the calendar title or presenting Case B.

### F-09/F-10 — Live viewer session resume (`live.js`)
- URL `session_id` is only resumed when session is open **and** belongs to the pane's book.
- `continueNewSession()` removes stale `session_id` from the URL via `history.replaceState`.

### F-15 — Settings validation (`settings_routes.py`)
- `pace_unit` must be `chars_per_hour` or `pages_per_hour`.
- Interval settings must be integers ≥ 1.

### F-17 — Heartbeat delta preservation (`live.js`)
`pendingActiveDelta` is decremented only after a successful heartbeat response, not before the request.

---

## Regression tests added

| Test | File |
|------|------|
| `test_paginate_txt_escapes_html_in_paragraphs` | `tests/test_pagination.py` |
| `test_start_session_reuses_open_session_from_direct_path` | `tests/test_routes_schedule.py` |
| `test_start_session_honors_resolved_book_id` | `tests/test_routes_schedule.py` |
| `test_patch_settings_rejects_invalid_pace_unit` | `tests/test_routes_settings.py` |
| `test_patch_settings_rejects_non_positive_interval` | `tests/test_routes_settings.py` |
| `test_patch_settings_rejects_non_integer_interval` | `tests/test_routes_settings.py` |

---

## Deferred items (Phase 7+)

- F-13/F-14: ICS timezone and partial-failure hardening
- F-18: Schedule notes field UX polish
- F-19: Book detail page enhancements per Phase 7 plan

---

## Re-audit checklist (Opus pass 2)

Verify the following are **closed**:

- [ ] No unescaped user text in paginated TXT output
- [ ] No duplicate open sessions across schedule + direct API paths
- [ ] All DB writers use `db_lock`
- [ ] Schedule `start_session` honors manual resolution
- [ ] Live viewer split-pane session binding is per-book
- [ ] Settings reject garbage interval/pace values
- [ ] Heartbeat deltas survive 409 auto-close

---

## Sign-off

| Role | Status |
|------|--------|
| Primary audit (Opus) | Complete — 19 findings |
| Validation (Codex) | Complete — prioritized FIX NOW list |
| Implementation | Complete — 12 findings fixed, 1 rejected, 4 deferred |
| Re-audit (Opus) | **GO** — all fixed items verified; jit ingest lock gap closed in follow-up commit |
| Test suite | **184 passed, 2 skipped** |
