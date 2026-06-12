# Studio App — Implementation Roadmap

> **For agentic workers:** This is a roadmap, not an executable plan. Each phase has its own plan file written immediately before its execution. The Phase 1 plan exists today (`2026-06-12-phase-1-foundation.md`); Phases 2–7 plans are written after their predecessor ships and we have ground truth to plan against.

**Spec:** [`docs/superpowers/specs/2026-06-12-studio-app-design.md`](../specs/2026-06-12-studio-app-design.md)

**Why phased:** the spec describes seven independent subsystems. Phasing produces working software at every checkpoint, avoids long-lived branches, and lets the next phase's plan adapt to whatever the previous phase actually built.

---

## Phase boundaries

| # | Name | Ships | Plan file |
|---|---|---|---|
| 1 | Foundation & Book Ingest | FastAPI app boots, settings + first-run wizard, full schema migrated, parser-backed book upload + library list page | `2026-06-12-phase-1-foundation.md` |
| 2 | Library Screens & CRUD | Library tabs (books / narrators / publishers), book detail screen, narrator detail screen, manual assignment | `2026-06-12-phase-2-library-screens.md` |
| 3 | Audio Scanner & Stats | Audio folder scanning via mutagen, `book_stats` + `narrator_stats` recompute, background scheduler thread | `2026-06-12-phase-3-audio-scanner.md` |
| 4 | Live Viewer | DOCX/TXT pagination, three viewer adapters (PDF / EPUB / HTML), reading_session lifecycle, heartbeat, reaper, marks, hotkeys, split view | tbd |
| 5 | Schedule & Calendar | `schedule_item` CRUD for manual rows, ICS poller, two studio lanes, [Start Session] resolution, JIT onboarding wizard | tbd |
| 6 | Sync & Backup | Snapshot job, marks.json mirror, cold-start recovery, sync status UI | tbd |
| 7 | Reports & Polish | Streamed CSV exports, exports cleanup, settings page, app.log rotation | tbd |

Each phase ends with a manually-verifiable demo. The acceptance demo is what determines "done"; tests verify the slices.

---

## Cross-cutting rules (all phases)

- **TDD throughout.** Failing test before implementation, every time.
- **DRY, YAGNI.** No abstractions until the second use justifies one.
- **One commit per task** (the final step of each task). Small, reviewable.
- **No new top-level dependencies without a recorded reason.** Add to `pyproject.toml` only when a task needs them.
- **Reuse existing parser.** `book_analyzer` is imported as a module; CLI stays as a separate entry point. No copy-paste.
- **Python 3.11+** (pyproject already targets this).
- **All paths absolute on disk.** Slugs are URL/filesystem-safe.

## Out of scope for the whole roadmap

- Auth, multi-user, sharing.
- Drive API, Calendar API.
- Audio recording, DAW integration.
- Mobile / responsive design.

---

## Phase 1 acceptance demo (end of Phase 1)

1. Fresh checkout, `uv sync` (or `pip install -e .[studio]`).
2. `python -m studio_app` → opens browser to `http://localhost:8765/setup` first-run wizard.
3. Pick a `data_root` (any folder). Wizard creates the folder structure.
4. Land on `/library` showing empty book list.
5. Click "Add book", upload a `.pdf` / `.epub` / `.docx` / `.txt` from the existing repo samples. Parser runs; the new book appears in the list with title, format, page count, body chars.
6. Click the book → see detail page with stats and "Re-run parser" button.
7. Restart the app; library still shows the book (state survived).

That demo is the Phase 1 done-bar.
