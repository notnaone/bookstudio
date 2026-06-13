# Agent Handoff — Audiobook Studio App

> **Drop this entire file into a new chat session to pick up where the previous one left off.** All 7 phases shipped on `master` at v1.0.0.

---

## Project in one paragraph

A local FastAPI web app for managing an audiobook recording studio. Single user (audio engineer), single machine (Windows). Wraps the existing `book_analyzer` parser (PDF/EPUB/DOCX/TXT) and adds: book/narrator/publisher catalog, planned schedule, custom in-browser book viewer with rectangle annotations, audio-folder scanning for pace stats, and Google Calendar (read-only via ICS) for studio bookings. Backup is done by Google Drive Desktop syncing the data folder. The app is structured as seven independently-shippable phases.

## Where everything lives

```
C:\Users\Kasutaja\Desktop\Anton\book parser\
├── book_analyzer/                          # existing parser (Phase 0 — don't modify)
├── studio_app/                             # new app, grown across phases
│   ├── main.py                             # FastAPI app factory + uvicorn entrypoint
│   ├── db.py                               # sqlite3 connect + migration runner
│   ├── settings.py                         # AppSettings dataclass + load/save_key
│   ├── slug.py                             # slugify(title)
│   ├── ingest.py                           # ingest_book(): copy → parse → DB row
│   ├── parser_adapter.py                   # thin shim over book_analyzer
│   ├── routes/                             # FastAPI routers
│   │   ├── system.py                       # /api/heartbeat
│   │   ├── books.py                        # books CRUD + filters + PATCH
│   │   ├── narrators.py                    # narrators CRUD
│   │   ├── publishers.py                   # publishers CRUD
│   │   └── settings_routes.py              # /api/settings, /api/setup wizard
│   ├── migrations/001_initial.sql          # locked schema (don't migrate, replace via new file)
│   └── static/                             # vanilla JS + HTML + CSS, no bundler
├── tests/                                  # pytest + httpx AsyncClient
│   ├── conftest.py                         # data_root / local_state_dir / conn / app / client fixtures
│   ├── fixtures/sample.txt
│   └── test_*.py
└── docs/superpowers/
    ├── specs/2026-06-12-studio-app-design.md          # locked design
    ├── plans/
    │   ├── 2026-06-12-studio-app-roadmap.md           # 7-phase overview
    │   ├── 2026-06-12-phase-1-foundation.md           # ✅ shipped
    │   ├── 2026-06-12-phase-2-library-screens.md      # ✅ shipped
    │   ├── 2026-06-12-phase-3-audio-scanner.md        # ✅ shipped
    │   ├── 2026-06-12-phase-4-live-viewer.md          # ✅ shipped
    │   ├── 2026-06-12-phase-5-schedule-calendar.md    # ✅ shipped
    │   └── (phases 6-7 to be written just-in-time per phase)
    └── progress/                                       # per-phase execution ledgers
```

## What's shipped (don't re-derive)

- **Phase 1 — Foundation:** FastAPI on `127.0.0.1:8765`, SQLite (WAL, FK on), all 12 tables + indexes from the spec, first-run `/setup` wizard, book upload+ingest, minimal library page. End-to-end demo verified live.
- **Phase 2 — Library Screens & CRUD:** Publishers + Narrators CRUD, `PATCH /api/books/:id` with status/genre/narrator/publisher/etc., draft-clear gate, `narrator_book` history wiring (SAVEPOINT-wrapped), library tabs UI with filters, narrator detail screen, editable book detail form.
- **Phase 3 — Audio Scanner & Stats:** Background `AudioScanner` thread, per-book folder scan via mutagen, `book_stats`/`narrator_stats` recompute, stats in book/narrator GET, `POST /rescan_audio`, UI stats panels + Re-scan button.
- **Phase 4 — Live Viewer:** DOM-aware pagination, viewer routes, marks CRUD + JSON mirror, reading_session API, SessionReaper, live HTML/JS shell with PDF/EPUB/HTML adapters, hotkeys, split view, "Open in viewer" from book detail.
- **Phase 6 — Sync & Backup:** SnapshotJob (live → `data_root/studio.sqlite`), cold-start recovery from snapshot, `data_root.txt` pointer, library snapshot status indicator, `POST /api/snapshot`.
- **Phase 7 — Reports & Polish:** CSV exports (stream + save), export cleanup, full settings page, marks.json restore, log rotation, wizard polish. Audit: `docs/superpowers/audits/2026-06-12-phase-7-audit-report.md`.
- **Cumulative tests:** 198 passed + 2 skipped on `master` (Phase 7 complete, v1.0.0).

The two skipped tests are documented:
1. SQLite migration rollback (Python `sqlite3.executescript` doesn't honor a single transaction across DDL).
2. Ingest INSERT rollback (`sqlite3.Connection.execute` is C-level and not monkeypatchable).

Both behaviors are verifiable by code review of the relevant try/except blocks.

## Git layout

```
master                       All 7 phases merged; 198 tests; tag v1.0.0
```

Each phase = its own branch off `master`, merged with `--no-ff` after audit passes. Per-task commits land on the phase branch. Branch naming: `phase-N-<short-name>`.

## The execution loop (per task)

This is the rhythm. Don't deviate without reason.

```
1. Pick the next task from the current phase plan.
2. Dispatch a single Composer implementer subagent. Give it:
   - Full task text copied from the plan (don't make it read the plan file)
   - Working dir + branch name
   - Previous commit SHA so it has context
   - Discipline rules (which files to touch, which NOT to)
   - Explicit "report SHA + git log -1 --stat back"
3. Verify the implementer's commit:
   - Run `uv run pytest -q` and confirm the cumulative target.
   - For substantial logic, dispatch a second Composer (separate subagent) for
     spec + quality review. For trivial copy-paste tasks, self-verify.
4. If review finds a real bug, dispatch a Composer fix subagent with precise
   instructions. Then re-verify.
5. Update the phase progress ledger (`docs/superpowers/progress/<phase>.md`).
6. Commit the ledger update with `docs(progress): <task> done`.
7. Mark the TaskList entry completed; start the next.
```

When all tasks pass: Opus (you) does the **phase audit**:
- Run the full suite.
- Boot the app via `uv run studio-app` in the background.
- Use curl to exercise the demo flow named in the plan's "done-criteria".
- Read the new/changed source files end-to-end. Find issues a Haiku reviewer would miss.
- Apply small surgical hardening fixes inline (or dispatch one Composer for them).
- Merge the phase branch to `master` with `--no-ff` and a summary message.
- Create the next phase branch and write its plan.

## Subagent dispatch — what works

- **Model:** `composer-2.5-fast` for everything (implementer, reviewers, fix loops).
- **Type:** `general-purpose` agent.
- **Foreground.** Don't background subagent dispatches — you need their result before the next step.
- **Prompt construction:** brief them like a smart colleague who walked in cold. They don't see this conversation. Include exact code blocks for every step. Don't write "implement the function" — paste the function body.
- **Discipline lines:** every dispatch should list which files are in scope and which are explicitly forbidden. Subagents respect this.
- **`SendMessage` is for cross-CCD-session messaging, NOT for continuing a subagent.** To continue a fix loop, dispatch a fresh Composer with specific repair instructions.

## When to push back on feedback

The user periodically pastes audit-style feedback (sometimes from another model). **Evaluate each point on merit before accepting.** Past examples of valid pushback:

- "SQLite trigger recursion" — turned out NOT to be a real bug (recursive_triggers defaults to OFF).
- "`_safe_int` for settings" — YAGNI; silent fallback hides config errors. Loud failure is correct.
- "Switch root() to app.state.conn" — accepted (consistency + correctness).
- "Stream uploads chunked" — accepted (cheap, future-proof).

Don't blindly apply. Don't blindly reject. Say which you accept and why, and which you don't and why.

## Skills currently in play (Claude Code plugin: superpowers)

- `superpowers:writing-plans` — drafts per-phase plan files.
- `superpowers:subagent-driven-development` — the per-task implementer/reviewer loop.
- `superpowers:brainstorming` — already done (produced the design spec).
- `superpowers:test-driven-development` — implementers follow it because we hand them failing tests.
- `superpowers:verification-before-completion` — relevant when you claim a phase done.

You don't need to re-invoke these. The pattern is established.

## Conventions to keep

- **TDD always.** Failing test first, then implementation, then commit.
- **One commit per task.** Plus one tiny ledger-update commit.
- **No emojis in code or commit messages** (the user has caveman mode active — terse text only). Tables and ASCII work.
- **No backwards-compat hacks** in implementation. Replace the old code; don't leave both versions.
- **Don't create READMEs, CONTRIBUTING.md, or extra docs** unless asked. Specs/plans/progress ledger only.
- **`uv` for all Python operations.** Never call `pip` or `python` directly when a `uv run` equivalent works.

## Pace + spend awareness

When blocked by platform limits, apply small surgical fixes inline (you, Opus) rather than dispatching another subagent.

Phase 7 complete. v1.0.0 tagged on master.

## What to do right now

1. `git fetch origin && git checkout master && git pull`.
2. Confirm `uv run pytest -q` → 198 passed + 2 skipped.
3. Optional: PyInstaller bundle per phase-7 plan.

See also `docs/superpowers/START_HERE.md` for a copy-paste cloud kickoff block.

---

**Spec is locked. Schema is locked. Demo flow is locked. Just keep shipping phases.**
