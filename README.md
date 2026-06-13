# Book Analyzer / BookStudio

This repository contains two applications:

1. **Book Analyzer** — desktop PySide6 GUI for narrators (legacy portable `.exe`)
2. **BookStudio (`studio_app`)** — local FastAPI web app for the recording engineer

---

## BookStudio (studio app)

Local audiobook studio manager: book catalog, live viewer, schedule (ICS), audio scanning, SQLite snapshot backup.

### Install

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### Run

```bash
uv run studio-app
```

Opens `http://127.0.0.1:8765`. First launch runs the `/setup` wizard to pick `data_root`.

### Data locations

| Path | Role |
|------|------|
| `~/AppData/Roaming/StudioApp/studio.live.sqlite` | Live WAL database (Windows default) |
| `<data_root>/studio.sqlite` | Google Drive–synced snapshot |
| `<data_root>/books/<slug>/` | Source, paginated view, `marks.json` |
| `<data_root>/exports/` | Optional CSV copies when `?save=1` |
| `<data_root>/app.log` | Rotating application log |

Put `data_root` inside a Google Drive Desktop folder for automatic off-machine backup.

### Tests

```bash
uv run pytest -q
```

---

## Book Analyzer (desktop GUI)

Desktop app for audiobook narrators. Parses a book (txt / docx / epub / pdf),
tracks reading progress against recorded audio, and computes pacing per
narrator.

Built with PySide6. Runs as a portable Windows `.exe` — all data lives in a
folder next to the program.

## Features

- **Library** — books are content-hashed (SHA-1) so the same file is
  recognized regardless of name or path. Re-opening a book is instant; no
  re-parse.
- **Hero progress card** — big % narrated, inline-editable current page and
  recorded hours, live readouts: recorded · remaining · tempo (body + raw) ·
  estimated total.
- **Book details** — file, format, pages, images, tables, body/raw character
  counts, chars-per-page.
- **Narrators** — typed or picked from history. Each completed book
  contributes to the narrator's average chars/hour.
- **Audio scanning** — point at a folder, `mutagen` recursively sums every
  audio file's duration (`.mp3 .wav .flac .m4a .aac .ogg .opus .wma .mp4
  .aiff`). Auto-scan on book open if enabled per book.
- **Sources** — local file (drag-drop anywhere on the window, Browse, or
  paste path), direct `http(s)://` URL, or Google Drive share link.
- **Visual element verification** — every image / table is logged with page,
  chapter, % through book, and surrounding text context for placement
  spot-check.

## Where your data lives

All data sits beside the program in a `BookAnalyzerData/` folder:

```
BookAnalyzerData/
├── index.json                   ← library catalogue (titles + summaries)
├── narrators.json               ← narrator history + avg chars/hour
└── books/
    ├── <book-id>.json           ← full parse result for one book
    └── <book-id>.progress.json  ← page, audio hours, narrator, completion
```

**Frozen exe** → folder lives in the same directory as `BookAnalyzer.exe`.
**Source run** → folder lives at the repo root.

This makes the install **fully portable** — copy the folder to a USB stick
together with the `.exe` and your library moves with you.

> Older installs that wrote to `%APPDATA%\BookAnalyzer\` won't migrate
> automatically. Copy that folder's contents into the new
> `BookAnalyzerData/` if you want to keep the history.

## Running from source

Requirements: Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run book-analyzer-gui
```

Or the CLI:

```powershell
uv run book-analyzer parse "C:\path\to\book.pdf"
uv run book-analyzer plan  "C:\path\to\book.metadata.json"
```

## Building the Windows `.exe`

```powershell
uv sync --extra build
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

Output: `dist\BookAnalyzer.exe` — single-file, no console window. Drop it
anywhere; on first run it creates `BookAnalyzerData/` next to itself.

## Project layout

```
book_analyzer/
├── gui.py            ← PySide6 GUI (main entry)
├── main.py           ← CLI (parse / plan subcommands)
├── library.py        ← persistent on-disk library (books, narrators)
├── audio_scan.py     ← mutagen-based folder duration sum
├── schema.py         ← dataclasses (BookMetadata, VisualElement, Progress)
├── reporter.py       ← CLI summary / plan renderer
└── parsers/
    ├── base.py
    ├── txt_parser.py     ← charset-normalizer encoding detect
    ├── docx_parser.py    ← block-order traversal, image alt + dims
    ├── epub_parser.py    ← spine walk, table rows×cols
    └── pdf_parser.py     ← pdfplumber, regex chapter detection
```

## Notes

- **Char counts**: both `raw_character_count` (whitespace incl.) and
  `body_character_count` (whitespace stripped) are stored. Tempo + planning
  use body chars.
- **PDF offsets** are flagged `approximate` — reading order in PDFs is
  heuristic.
- **Chapter detection** in PDF uses strict regex (`Chapter N`, `Peatükk N`,
  `Глава N`, named sections like `Prologue` / `Sissejuhatus`). The previous
  font-size heuristic was dropped — it over-triggered on body text.
- **Google Drive** download uses `gdown`. Files must be shared
  *"Anyone with the link"*; OAuth-only files won't work.
