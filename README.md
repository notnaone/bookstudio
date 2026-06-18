# BookStudio

A local web app for managing an audiobook recording studio. Tracks books, narrators, recording sessions, audio files, and studio schedules — all offline, all yours.

No cloud required. Data lives in SQLite on your machine (or inside a synced Google Drive folder for off-machine backup).

---

## What it does

- **Book catalog** — Import and manage books (TXT, DOCX, EPUB, PDF); content-hashed deduplication; paginated viewer
- **Narrators & publishers** — Link books to narrators and publishers; track assignments
- **Session tracking** — Log recording sessions per book; auto-detect session state (idle timeout)
- **Audio scanner** — Watches the data folder for recorded audio; computes pacing (chars/hour) per narrator
- **Schedule (ICS)** — Polls studio calendar feeds (iCal/ICS); auto-resolves studio assignments per book
- **Live viewer** — Real-time book reader synced to recording position; highlights current sentence
- **Snapshots** — Periodic SQLite snapshots to a Google Drive folder for automatic backup
- **Reports & exports** — CSV exports of books, sessions, pacing data

---

## Architecture

Single-process Python app: FastAPI backend + plain HTML/JS/CSS frontend served locally.

```
studio_app/         — FastAPI app (routes, background workers, DB, settings)
  routes/           — API endpoints: books, narrators, sessions, schedule, exports, system
  static/           — Vanilla JS/CSS frontend (no build step)
  migrations/       — SQLite schema migrations
book_analyzer/      — Standalone book parser (TXT/DOCX/EPUB/PDF) + desktop GUI
tests/              — pytest suite (~25 test modules, fixtures, conftest)
```

**Storage:** SQLite (WAL mode) — live DB in `AppData`, snapshot in data root
**Background workers:** calendar poller, audio scanner, session reaper, snapshot writer
**No external services required** — all data is local

---

## Tech stack

| | |
|-|-|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Frontend | Vanilla JS, HTML, CSS (no framework, no build step) |
| Database | SQLite (WAL mode, thread-safe locking) |
| Parsing | python-docx, ebooklib, pdfplumber, mammoth |
| Calendar | icalendar, httpx |
| Audio | mutagen |
| Packaging | uv, pyproject.toml |
| Tests | pytest |

---

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/notnaone/bookstudio
cd bookstudio
uv sync
uv run studio-app
```

Opens `http://127.0.0.1:8765`. First launch runs the setup wizard to pick a `data_root` folder.

Put `data_root` inside a Google Drive Desktop folder for automatic off-machine backup.

---

## Data locations (Windows defaults)

| Path | Role |
|------|------|
| `~/AppData/Roaming/StudioApp/studio.live.sqlite` | Live WAL database |
| `<data_root>/studio.sqlite` | Snapshot (synced via Drive) |
| `<data_root>/books/<slug>/` | Book source files + marks |
| `<data_root>/exports/` | CSV exports |
| `<data_root>/app.log` | Rotating log |

---

## Tests

```bash
uv run pytest -q
```

---

## Status

Personal tooling project. Built for a real audiobook recording studio. Not a general-purpose product.
