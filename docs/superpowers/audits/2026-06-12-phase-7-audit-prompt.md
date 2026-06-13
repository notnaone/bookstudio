# BookStudio — Phase 7 Audit Prompt (Opus / Codex)

> **Purpose:** Post-Phase-7 audit of Reports & Polish deliverables on `phase-7-reports-polish`. Verify CSV exports, settings UI, marks restore, log rotation, and polish items match the locked spec.

---

## 1. Scope (Phase 7 only)

**New modules:**
- `studio_app/exports.py` — CSV row generators
- `studio_app/routes/exports.py` — streaming endpoints + cleanup
- `studio_app/marks_restore.py` — JSON sidecar → DB
- `studio_app/log_setup.py` — rotating `app.log`
- `studio_app/static/settings.js` — full settings page

**Modified:**
- `studio_app/main.py` — exports router, `configure_logging`
- `studio_app/routes/system.py` — `POST /api/marks/restore`
- `studio_app/static/settings.html`, `setup.html`, `live.js`, `live.html`, `app.js`
- `README.md` — Studio App section

**Test baseline:** 195 passed, 2 skipped

**Authoritative spec:** `docs/superpowers/specs/2026-06-12-studio-app-design.md` §6.2 Export bar, §6 Settings, §10 Mark restoration, §12 app.log

**Phase plan:** `docs/superpowers/plans/2026-06-12-phase-7-reports-polish.md`

---

## 2. Verify each deliverable

### 2.1 CSV exports (Tasks 0–1)

| Check | Expected |
|-------|----------|
| Column order stable | Same header every run |
| Books JOIN | publisher_name, narrator_name, hours_recorded from stats |
| Sessions union | reading + work_session with kind column |
| Filters | status, date range, kind, book_id |
| Streaming | `StreamingResponse` generator, not full buffer |
| save=1 | Writes to `data_root/exports/<scope>-<timestamp>.csv` when dir exists |
| Cleanup | `POST /api/export/cleanup` deletes by mtime age |

### 2.2 Settings UI (Task 2)

| Field / action | API |
|----------------|-----|
| data_root | PATCH /api/settings |
| ics_url_studio_1/2 | PATCH |
| pace_unit + 5 intervals | PATCH with validation |
| Test calendar | PATCH ICS if changed, then POST /api/schedule/refresh |
| Snapshot now | POST /api/snapshot |
| Export cleanup | POST /api/export/cleanup |
| Restore marks | POST /api/marks/restore |
| Export download links | GET /api/export/*.csv |

### 2.3 Marks restore (Task 3)

- Walks `data_root/books/<slug>/marks.json`
- INSERT only when no matching row (book_id + page + coords)
- Returns `{restored, skipped_existing, errors}`
- Uses `db_lock`

### 2.4 Log rotation (Task 4)

- `RotatingFileHandler` 10MB × 3 backups at `data_root/app.log`
- Called from `main()` only, not in tests
- Stderr StreamHandler retained

### 2.5 Polish (Task 5)

- Setup wizard: optional ICS + narrator
- Live viewer: session id label, Ctrl+F → search input
- Library nav already has Settings link

---

## 3. Security & correctness

- CSV injection (formula cells starting with `=`)
- Path traversal in cleanup (only `exports/*.csv`)
- Concurrent restore + mark writes (db_lock)
- Export endpoints bypass db_lock? (read-only OK)
- Settings data_root change without restart warning

---

## 4. Output format

```markdown
## Findings

| ID | Sev | File | Summary |
|----|-----|------|---------|

## Deferred (OK)
...

## Merge verdict
GO / NO-GO
```

Severity: BLOCKER | MAJOR | MINOR | DEFERRED

Do not report missing Phase 8 features or schema changes.
