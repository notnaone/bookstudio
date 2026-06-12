"""Persistent on-disk library: scanned books + per-book reading progress.

Storage layout (per OS):
    %APPDATA%/BookAnalyzer/
        index.json                # quick title list
        books/<book_id>.json      # full ParseResult dict
        books/<book_id>.progress.json
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .schema import BookMetadata, Location, ParseResult, Progress, VisualElement


def _data_dir() -> Path:
    """Local data folder, lives next to the program.

    - Frozen exe  → directory of the .exe
    - Source run  → project root (parent of the `book_analyzer` package)

    Result: a portable `BookAnalyzerData/` folder beside the program holding
    `index.json`, `narrators.json`, and `books/*.json`.
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / "BookAnalyzerData"


def compute_book_id(path: Path) -> str:
    """SHA1 of file content. Stable across renames."""
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Library:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _data_dir()
        self.books_dir = self.root / "books"
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.narrators_path = self.root / "narrators.json"

    # ──────────── index ────────────

    def _read_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_index(self, idx: dict[str, dict]) -> None:
        self.index_path.write_text(
            json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def list_books(self) -> list[dict]:
        """Returns [{book_id, file_name, added_at, body_chars, total_pages}, …]."""
        idx = self._read_index()
        items = list(idx.values())
        items.sort(key=lambda x: x.get("added_at", ""), reverse=True)
        return items

    # ──────────── metadata ────────────

    def _meta_path(self, book_id: str) -> Path:
        return self.books_dir / f"{book_id}.json"

    def _progress_path(self, book_id: str) -> Path:
        return self.books_dir / f"{book_id}.progress.json"

    def has_book(self, book_id: str) -> bool:
        return self._meta_path(book_id).exists()

    def save_metadata(self, result: ParseResult) -> None:
        book_id = result.book_metadata.book_id
        if not book_id:
            raise ValueError("BookMetadata.book_id must be set before saving.")
        self._meta_path(book_id).write_text(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        idx = self._read_index()
        idx[book_id] = {
            "book_id": book_id,
            "file_name": result.book_metadata.file_name,
            "body_chars": result.book_metadata.body_character_count,
            "total_pages": result.book_metadata.total_pages,
            "added_at": idx.get(book_id, {}).get("added_at")
            or _dt.datetime.now().isoformat(timespec="seconds"),
            "last_seen": _dt.datetime.now().isoformat(timespec="seconds"),
        }
        self._write_index(idx)

    def load_metadata(self, book_id: str) -> ParseResult:
        data = json.loads(self._meta_path(book_id).read_text(encoding="utf-8"))
        meta = BookMetadata(**data["book_metadata"])
        ves: list[VisualElement] = []
        for v in data.get("visual_elements", []):
            loc = Location(**v.pop("location"))
            ves.append(VisualElement(location=loc, **v))
        return ParseResult(book_metadata=meta, visual_elements=ves, chapters=data.get("chapters", []))

    def delete_book(self, book_id: str) -> None:
        for p in (self._meta_path(book_id), self._progress_path(book_id)):
            if p.exists():
                p.unlink()
        idx = self._read_index()
        idx.pop(book_id, None)
        self._write_index(idx)

    # ──────────── progress ────────────

    def load_progress(self, book_id: str) -> Progress:
        p = self._progress_path(book_id)
        if not p.exists():
            return Progress()
        try:
            return Progress(**json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, TypeError):
            return Progress()

    def save_progress(self, book_id: str, progress: Progress) -> None:
        progress.updated_at = _dt.datetime.now().isoformat(timespec="seconds")
        self._progress_path(book_id).write_text(
            json.dumps(asdict(progress), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ──────────── narrators ────────────

    def _read_narrators(self) -> dict[str, dict]:
        if not self.narrators_path.exists():
            return {}
        try:
            return json.loads(self.narrators_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _write_narrators(self, data: dict[str, dict]) -> None:
        self.narrators_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def list_narrators(self) -> list[dict]:
        """[{name, avg_chars_per_hour, book_count}, …] sorted by name."""
        data = self._read_narrators()
        out = []
        for name, entry in data.items():
            tempos = entry.get("tempos", [])
            avg = (
                sum(t["chars_per_hour"] for t in tempos) / len(tempos)
                if tempos
                else 0.0
            )
            out.append(
                {"name": name, "avg_chars_per_hour": avg, "book_count": len(tempos)}
            )
        out.sort(key=lambda x: x["name"].lower())
        return out

    def get_narrator(self, name: str) -> dict | None:
        data = self._read_narrators()
        entry = data.get(name)
        if not entry:
            return None
        tempos = entry.get("tempos", [])
        avg = (
            sum(t["chars_per_hour"] for t in tempos) / len(tempos)
            if tempos
            else 0.0
        )
        return {
            "name": name,
            "avg_chars_per_hour": avg,
            "book_count": len(tempos),
            "tempos": tempos,
        }

    def ensure_narrator(self, name: str) -> None:
        """Create an empty narrator record if absent."""
        name = name.strip()
        if not name:
            return
        data = self._read_narrators()
        if name not in data:
            data[name] = {
                "tempos": [],
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            }
            self._write_narrators(data)

    def record_narrator_tempo(
        self, name: str, book_id: str, chars_per_hour: float
    ) -> None:
        """Append a finished-book tempo entry; replaces prior entry for same book."""
        name = name.strip()
        if not name or chars_per_hour <= 0:
            return
        data = self._read_narrators()
        entry = data.setdefault(
            name,
            {
                "tempos": [],
                "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
            },
        )
        tempos = [t for t in entry.get("tempos", []) if t.get("book_id") != book_id]
        tempos.append(
            {
                "book_id": book_id,
                "chars_per_hour": chars_per_hour,
                "completed_at": _dt.datetime.now().isoformat(timespec="seconds"),
            }
        )
        entry["tempos"] = tempos
        data[name] = entry
        self._write_narrators(data)
