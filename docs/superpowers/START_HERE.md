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

If you do, pull the latest master:
    git fetch origin
    git checkout master
    git pull

## Step 2 — Sanity-check the environment

    uv sync --all-groups
    uv run pytest -q
Expected: 178 passed + 2 skipped.

If pytest doesn't show that, STOP and ask before changing anything.

## Step 3 — Read these files, in this order

1. docs/superpowers/AGENT_HANDOFF.md
2. docs/superpowers/specs/2026-06-12-studio-app-design.md
3. docs/superpowers/plans/2026-06-12-studio-app-roadmap.md
4. docs/superpowers/progress/2026-06-12-phase-5.md   (last completed phase ledger)
5. docs/superpowers/plans/2026-06-12-phase-6-sync-backup.md

Do NOT read every file under studio_app/ end-to-end yet. Read on demand.

## Step 4 — Pick up where the previous session stopped

Phases 1–5 are shipped on master. Phase 6 (Sync & Backup) is next.

Follow the execution loop documented in AGENT_HANDOFF.md (section
"The execution loop"):

  - Create branch phase-6-sync-backup off master.
  - Read the Phase 6 plan; create a progress ledger.
  - Dispatch Composer for Task 0 onward.

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

## What NOT to do

- Don't try to design or change the spec — it's locked.
- Don't migrate or change the schema — Phase 1's 001_initial.sql is
  the locked schema.
- Don't add features beyond the current phase's plan.
- Don't change book_analyzer/ — it's the existing dependency.
- Don't commit to master directly; always merge from a phase branch.

Now begin with Phase 6 (or Task 0 if the ledger already exists).
```

---

## Notes for the human pasting this

- Cloud agents: clone from GitHub, checkout `master`, run Step 2, then paste the block above.
- The handoff doc is the source of truth. When in doubt, point the agent at `docs/superpowers/AGENT_HANDOFF.md`.
- Current baseline on `master`: Phase 5 + audit hardening shipped (168 tests).
