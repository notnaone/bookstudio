# BookStudio — Phase 7 Audit Report

**Date:** 2026-06-13  
**Branch:** `phase-7-reports-polish`  
**Test baseline:** 198 passed, 2 skipped

---

## Pipeline

| Stage | Agent | Result |
|-------|-------|--------|
| Audit prompt | Composer | `docs/superpowers/audits/2026-06-12-phase-7-audit-prompt.md` |
| Primary audit | Opus 4.7 | 18 findings (P7-F-01–P7-F-18), initial **NO-GO** |
| Validation | Codex | Confirmed CSV injection, pace-unit mismatch, save=1 silent no-op |
| Hardening | Composer | P0/P1 fixes applied |
| Re-audit | Opus 4.7 | **GO** (see below) |

---

## Primary findings + resolution

| ID | Sev | Summary | Resolution |
|----|-----|---------|------------|
| P7-F-01 | MAJOR | CSV formula injection | **Fixed** — `_csv_safe()` prefixes dangerous leading chars |
| P7-F-02 | MAJOR | Pace unit cycle 4 vs server 2 | **Fixed** — all 4 units in `settings_routes` + settings dropdown |
| P7-F-03 | MAJOR | Settings dropdown missing units | **Fixed** |
| P7-F-04 | MINOR | Partial file on disconnect during save=1 | Deferred — low risk local app |
| P7-F-05 | MINOR | bool accepted as older_than_days | **Fixed** — `type(x) is int` |
| P7-F-06 | MINOR | Filename timestamp mismatch | Deferred |
| P7-F-07 | MINOR | No UTF-8 BOM for Excel | Deferred |
| P7-F-08 | MINOR | Float drift on mark restore dedup | **Fixed** — round to 4 decimals |
| P7-F-09 | MINOR | cleanup on directories | **Fixed** — `is_file()` guard |
| P7-F-10 | MINOR | data_root restart warning | Existing static note retained |
| P7-F-11 | MINOR | Duplicate stderr with uvicorn | Deferred |
| P7-F-12 | MINOR | older_than_days=0 immediate wipe | Accepted — user sets days explicitly |
| P7-F-13 | MINOR | Calendar test 503 message | Deferred |
| P7-F-14 | MINOR | NULL started_at sort | Deferred |
| P7-F-15 | MINOR | Dot-dir noise in restore | **Fixed** — skip `.*` dirs |
| P7-F-16 | MINOR | Setup partial failure UX | Deferred |
| P7-F-17 | MINOR | Ctrl+F marks-only vs adapter search | Intentional per plan |
| P7-F-18 | DEFERRED | Export read-only without db_lock | OK |

### Codex F4 (save=1 silent no-op)

**Fixed** — `save=1` now `mkdir`s `data_root/exports/` when missing.

---

## Hardening commits

- CSV injection neutralization + regression test
- Pace units aligned with spec (4 values)
- Export save creates exports directory
- Cleanup bool guard + is_file filter
- Mark restore coord rounding + dot-dir skip

---

## Re-audit verdict

**GO** — Blockers P7-F-01/02/03 and Codex F4 resolved. Remaining items are minor/deferred polish appropriate for v1.0.0.

---

## Phase 7 deliverables (shipped)

- CSV exports: books, sessions, audio_files (stream + optional save)
- `POST /api/export/cleanup`
- Full `/settings` page
- `POST /api/marks/restore`
- Rotating `data_root/app.log`
- Setup wizard ICS + narrator options
- Live session id label + Ctrl+F
