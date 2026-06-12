# Session Kickoff Prompt

> **Copy the block below into a new cloud or local agent session.** It tells the agent where the project is, what to read, and what to do first. Everything else is in `AGENT_HANDOFF.md`.

---

```
You're picking up an in-flight project: BookStudio — a local FastAPI web app
for managing an audiobook recording studio. Single user, single Windows
machine, backup via Google Drive Desktop.

## Step 1 — Get the code

The repo is at https://github.com/notnaone/bookstudio.git.

If you don't have it locally yet:
    git clone https://github.com/notnaone/bookstudio.git
    cd bookstudio

If you do, pull the latest work branch:
    git fetch origin
    git checkout phase-3-audio-scanner
    git pull

## Step 2 — Sanity-check the environment

    uv sync --all-groups
    uv run pytest -q
Expected: 78 passed + 2 skipped (baseline before Task 1 lands).

If pytest doesn't show that, STOP and ask before changing anything.

## Step 3 — Read these files, in this order

1. docs/superpowers/AGENT_HANDOFF.md
2. docs/superpowers/specs/2026-06-12-studio-app-design.md
3. docs/superpowers/plans/2026-06-12-studio-app-roadmap.md
4. docs/superpowers/progress/2026-06-12-phase-3.md   (current phase ledger)
5. docs/superpowers/plans/2026-06-12-phase-3-audio-scanner.md

Do NOT read every file under studio_app/ end-to-end yet. Read on demand.

## Step 4 — Pick up where the previous session stopped

Branch: phase-3-audio-scanner (tip should include Task 0 + progress ledger).

Already done:
  - Phase 3 progress ledger at docs/superpowers/progress/2026-06-12-phase-3.md
  - Task 0: silent MP3 fixture (commit 628b81e)

Your next job:
  - Dispatch Composer for Phase 3 Task 1 (audio_scanner.scan_book)
  - Continue the loop in AGENT_HANDOFF.md: implementer → verify → review →
    ledger commit → next task

## Working conventions to keep

- Composer subagents (general-purpose, model="composer-2.5-fast") for all
  implementation and per-task review. Opus only for the phase audit at
  the end + small surgical fixes.
- TDD always: failing test first, then minimal code, then commit.
- One commit per task. Plus one tiny ledger-update commit.
- No emojis in code or commit messages.
- No new top-level files (READMEs, CONTRIBUTING.md) unless asked.
- Use uv for all Python operations.
- When user feedback arrives mid-phase, evaluate on merit. Push back when
  wrong, accept when right, explain which is which.

## When Phase 3 is done

Audit it yourself (Opus), apply small hardening inline, merge to master
with --no-ff, push to origin, switch to phase-4-live-viewer (already
planned), and continue the same loop.

## What NOT to do

- Don't try to design or change the spec — it's locked.
- Don't migrate or change the schema — Phase 1's 001_initial.sql is
  the locked schema.
- Don't add features beyond the current phase's plan.
- Don't change book_analyzer/ — it's the existing dependency.
- Don't commit to master directly; always merge from a phase branch.

Now begin with Task 1.
```

---

## Notes for the human pasting this

- Cloud agents: clone from GitHub, checkout `phase-3-audio-scanner`, run Step 2, then paste the block above.
- The handoff doc is the source of truth. When in doubt, point the agent at `docs/superpowers/AGENT_HANDOFF.md`.
- Current remote branch: `origin/phase-3-audio-scanner` (Phase 3 in progress).
