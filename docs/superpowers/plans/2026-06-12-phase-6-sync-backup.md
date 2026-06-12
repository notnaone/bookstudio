# Phase 6 — Sync & Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development.

**Goal:** Implement the snapshot job (live DB → `data_root/studio.sqlite` atomic copy), cold-start recovery from snapshot, marks.json mirror restoration safety, and a small sync-status UI indicator. End state: power-cut at any moment leaves either a clean live DB or a clean snapshot. Drive Desktop sees only fully-written files.

**Architecture:** A `SnapshotJob` daemon thread runs every `snapshot_interval_seconds` (default 300). Each iteration: `PRAGMA wal_checkpoint(TRUNCATE)`, SQLite online-backup API copies live → `studio.sqlite.tmp` → atomic rename → `studio.sqlite`. On startup, if `studio.live.sqlite` is missing or zero bytes and `data_root/studio.sqlite` exists, restore the snapshot before opening the live DB.

**Prereqs:** Phase 5 merged. Live DB is at `local_state_dir/studio.live.sqlite`; data root is at `app_setting.data_root`.

**6 tasks.**

---

## File structure

**New:**
```
studio_app/snapshot.py             # snapshot_now(live_path, snapshot_path), SnapshotJob
studio_app/recovery.py             # cold-start: maybe_restore_snapshot()
tests/test_snapshot.py
tests/test_recovery.py
```

**Modified:**
```
studio_app/main.py                 # call maybe_restore_snapshot() before migrate;
                                   # start SnapshotJob after build_app
studio_app/routes/system.py        # heartbeat reports last_snapshot_at
studio_app/static/library.html     # top bar: snapshot status indicator
studio_app/static/app.js           # poll /api/heartbeat for indicator
```

---

## Cross-cutting rules

- Snapshots use SQLite online-backup API (`conn.backup(dest_conn)`) — does NOT corrupt under concurrent writes.
- Always write to `studio.sqlite.tmp` then atomic rename. Drive Desktop must never see a partial file.
- Snapshot job is one-way: live → snapshot. Never the reverse, except in cold-start recovery before the live DB exists.

---

## Task 0: `snapshot_now` function

**Files:** `studio_app/snapshot.py`, `tests/test_snapshot.py`

- [ ] Implement:
  ```python
  def snapshot_now(live_path: Path, snapshot_path: Path) -> int:
      """Checkpoint WAL, online-backup to .tmp, rename. Returns bytes written."""
      # 1. Open live with sqlite3
      # 2. PRAGMA wal_checkpoint(TRUNCATE)
      # 3. Open dest at snapshot_path.with_suffix('.sqlite.tmp')
      # 4. live.backup(dest)
      # 5. dest.close(); live.close()
      # 6. tmp_path.replace(snapshot_path)
      # 7. return snapshot_path.stat().st_size
  ```
- [ ] Tests:
  - Write some data to live DB → snapshot → open snapshot independently → data present.
  - Snapshot in middle of WAL writes → no corruption (do a write between connect and backup; assert snapshot reflects last commit).
  - Pre-existing `.tmp` from prior crash gets overwritten cleanly.
- [ ] Commit: `feat(studio): snapshot_now via SQLite online backup`

---

## Task 1: SnapshotJob daemon

**Files:** `studio_app/snapshot.py` (append), `tests/test_snapshot.py` (append)

- [ ] `SnapshotJob(live_path, snapshot_path, interval_seconds)` — same daemon pattern as `AudioScanner` / `SessionReaper` / `CalendarPoller`. Calls `snapshot_now` on each iteration.
- [ ] `last_snapshot_at` attribute; `last_snapshot_bytes` attribute.
- [ ] Skip the iteration if the live file doesn't exist yet (early-startup race).
- [ ] Test: start with interval=0.5s, sleep 1s, assert at least one snapshot exists.
- [ ] Commit: `feat(studio): SnapshotJob daemon thread`

---

## Task 2: Cold-start recovery

**Files:** `studio_app/recovery.py`, `tests/test_recovery.py`

- [ ] Implement:
  ```python
  def maybe_restore_snapshot(
      live_path: Path, snapshot_path: Path
  ) -> Literal['fresh', 'restored', 'live_present']:
      """If live file is missing/empty and snapshot exists, copy snapshot → live.
      Returns the state taken."""
  ```
- [ ] Tests:
  - Both missing → `'fresh'`. (Migration will create live afterward.)
  - Live present (any size > 0) → `'live_present'`, snapshot untouched.
  - Live missing + snapshot present → `'restored'`. Live file equals snapshot bytes.
  - Live empty (0 bytes) + snapshot present → `'restored'`.
- [ ] Commit: `feat(studio): cold-start snapshot restoration`

---

## Task 3: Wire into main()

**Files:** `studio_app/main.py`

- [ ] `main()` sequence:
  1. Resolve `local_state_dir`, `data_root` (from previous run's app_setting if available — read snapshot to find it, or use defaults).
  2. Call `maybe_restore_snapshot(live_path, snapshot_path)`.
  3. `migrate(live_path)`.
  4. `connect(live_path)`.
  5. `build_app(...)`.
  6. Start `SnapshotJob`, `AudioScanner`, `SessionReaper`, `CalendarPoller`.
- [ ] Subtle: where does `data_root` come from at cold-start when there's no live DB and no snapshot yet (first-ever run)? Answer: use the `DEFAULT_LOCAL_STATE_DIR` as a fallback; `/setup` will overwrite it on first user action.
- [ ] When restoring from snapshot, `app_setting.data_root` is present in the snapshot → it'll be live after migrate.
- [ ] Commit: `feat(studio): main() wires snapshot restore + SnapshotJob`

---

## Task 4: Heartbeat reports last_snapshot_at + UI indicator

**Files:** `studio_app/routes/system.py`, `studio_app/static/library.html`, `studio_app/static/app.js`

- [ ] Heartbeat already has `last_snapshot_at: None`; replace with `getattr(request.app.state, 'snapshot_job', None).last_snapshot_at`.
- [ ] Library top bar: small text "Last snapshot: 2 min ago · [Snapshot now]". Button POSTs to `/api/snapshot` (next task).
- [ ] `app.js` polls `/api/heartbeat` every 30 s, updates indicator text. Color code:
  - Green: < 10 min since last snapshot.
  - Yellow: 10–30 min.
  - Red / stale chip: > 30 min.
- [ ] Test: heartbeat key changes after manual snapshot.
- [ ] Commit: `feat(studio): snapshot status indicator + heartbeat field`

---

## Task 5: `POST /api/snapshot` manual trigger

**Files:** `studio_app/routes/system.py`, tests

- [ ] Endpoint that invokes `app.state.snapshot_job.run_once()` (synchronously). Returns `{ok: true, bytes, snapshot_at}`. The daemon's loop still runs in the background; manual button just shortcuts the next iteration.
- [ ] Test: POST → 200 → snapshot file exists with timestamp.
- [ ] Commit: `feat(studio): POST /api/snapshot manual trigger`

---

## Phase 6 done-criteria

- [ ] Tests target ~165 passed + 2 skipped.
- [ ] Demo:
  1. Boot app, see "Last snapshot: never".
  2. Wait 5 min (or click "Snapshot now") → indicator updates.
  3. Kill the app mid-session (Ctrl+C).
  4. Delete `local_state_dir/studio.live.sqlite`.
  5. Restart → app boots from snapshot; library shows all books from before.
  6. Open `data_root/studio.sqlite` via sqlite CLI while app is running → no errors, valid DB.
  7. Drive Desktop tray icon shows the snapshot file uploading.

## Self-review

| Spec section | Where |
|---|---|
| §3.3 local_state vs data_root split | (already in Phase 1; this phase enforces it) |
| §5.1 Snapshot mechanism | Tasks 0 + 1 |
| §5.3 Sync status UI | Task 4 |
| §5.4 Cold-start recovery | Tasks 2 + 3 |
| §10 Drive daemon offline edge case | Acknowledged; we can't detect it. UI indicator shows only OUR snapshot freshness. |

**Deferred to Phase 7:**
- marks.json restoration tool (in case DB is gone but marks.json files survived).
- Export-folder cleanup is unrelated; goes to Phase 7.
