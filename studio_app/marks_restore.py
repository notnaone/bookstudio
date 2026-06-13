from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def restore_marks_from_disk(conn: sqlite3.Connection, data_root: Path) -> dict:
    """Rebuild mark rows from books/<slug>/marks.json sidecars."""
    books_dir = data_root / "books"
    restored = 0
    skipped_existing = 0
    errors: list[str] = []

    if not books_dir.is_dir():
        return {"restored": 0, "skipped_existing": 0, "errors": []}

    for book_dir in sorted(books_dir.iterdir()):
        if not book_dir.is_dir() or book_dir.name.startswith("."):
            continue
        marks_path = book_dir / "marks.json"
        if not marks_path.is_file():
            continue

        slug = book_dir.name
        row = conn.execute(
            "SELECT id FROM book WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            errors.append(f"{slug}: no matching book row")
            continue
        book_id = int(row["id"])

        try:
            raw = json.loads(marks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{slug}: {exc}")
            continue

        if not isinstance(raw, list):
            errors.append(f"{slug}: marks.json must be a JSON array")
            continue

        for item in raw:
            if not isinstance(item, dict):
                errors.append(f"{slug}: mark entry must be an object")
                continue
            try:
                page = int(item["page"])
                x_pct = round(float(item["x_pct"]), 4)
                y_pct = round(float(item["y_pct"]), 4)
                w_pct = round(float(item["w_pct"]), 4)
                h_pct = round(float(item["h_pct"]), 4)
            except (KeyError, TypeError, ValueError):
                errors.append(f"{slug}: invalid mark coordinates")
                continue

            existing = conn.execute(
                "SELECT id FROM mark"
                " WHERE book_id = ? AND page = ?"
                " AND x_pct = ? AND y_pct = ? AND w_pct = ? AND h_pct = ?",
                (book_id, page, x_pct, y_pct, w_pct, h_pct),
            ).fetchone()
            if existing is not None:
                skipped_existing += 1
                continue

            color = item.get("color", "#FFFF00")
            comment = item.get("comment")
            conn.execute(
                "INSERT INTO mark"
                " (book_id, page, x_pct, y_pct, w_pct, h_pct, color, comment)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (book_id, page, x_pct, y_pct, w_pct, h_pct, color, comment),
            )
            restored += 1

    return {
        "restored": restored,
        "skipped_existing": skipped_existing,
        "errors": errors,
    }
