# Session Kickoff Prompt

> **Copy the block below into a new agent session.** It tells the agent where the project is, what to read, and what to do first. Everything else is in `AGENT_HANDOFF.md`.

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
Expected: 78 passed + 2 skipped.

If pytest doesn't show that, STOP and ask before changing anything.

## Step 3 — Read these files, in this order

1. docs/superpowers/AGENT_HANDOFF.md          (full project context)
2. docs/superpowers/specs/2026-06-12-studio-app-design.md  (locked design)
3. docs/superpowers/plans/2026-06-12-studio-app-roadmap.md (phase index)
4. docs/superpowers/progress/2026-06-12-phase-2.md         (last completed
                                                            phase ledger)
5. docs/superpowers/plans/2026-06-12-phase-3-audio-scanner.md
                                                   (your current target)

Do NOT read every file under studio_app/ end-to-end yet. Read on demand.

## Step 4 — Pick up where the previous session stopped

Phases 1 and 2 are shipped and merged to master. The Phase 3 plan exists
and is fully TDD-ready. Your job is to execute it.

Switch to the Phase 3 branch:
    git checkout phase-3-audio-scanner

Then follow the execution loop documented in AGENT_HANDOFF.md (section
"The execution loop"):

  - Create a Phase 3 progress ledger at
    docs/superpowers/progress/2026-06-12-phase-3.md (copy Phase 2's
    template, blank out task statuses).
  - Create TaskList entries for Phase 3 Tasks 0–7 + one
    "Phase 3 audit + merge".
  - Dispatch the first Haiku implementer for Phase 3 Task 0
    (silent-MP3 fixture).
  - Continue the loop: implementer → verify → review (Haiku) → commit
    ledger → next task.

## Working conventions to keep

- Cheap Haiku subagents (general-purpose, model="haiku") for all
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

Now begin.
```

---

## Notes for the human pasting this

- The new session will need access to the Claude Code workspace tools or equivalent (Read, Edit, Bash, Agent for subagents). Make sure the runtime supports them.
- If you're using a different orchestrator (Codex, Aider, etc.), translate the conventions — TDD, per-task commits, Haiku for impl — into that platform's idioms.
- The handoff doc is the source of truth. Whenever in doubt, point the new agent back to `docs/superpowers/AGENT_HANDOFF.md`.
