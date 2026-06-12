from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from studio_app.pagination import paginate_docx, paginate_txt, write_pages_to_dir
from studio_app.parser_adapter import parse_book
from studio_app.slug import slugify


def _unique_slug(conn: sqlite3.Connection, base: str) -> str:
    candidate = base
    n = 2
    while conn.execute(
        "SELECT 1 FROM book WHERE slug = ?", (candidate,)
    ).fetchone() is not None:
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def ingest_book(
    conn: sqlite3.Connection,
    data_root: Path,
    source_file: Path,
    *,
    title: str,
    publisher_id: int | None = None,
    audio_folder: str | None = None,
    is_draft: bool = False,
    original_filename: str | None = None,
) -> int:
    """Copy `source_file` into the data_root, parse it, insert a book row.

    Returns the new book.id.
    """
    if not source_file.exists():
        raise FileNotFoundError(source_file)

    base_slug = slugify(title)
    slug = _unique_slug(conn, base_slug)

    book_dir = data_root / "books" / slug
    src_dir = book_dir / "source"
    view_dir = book_dir / "view"
    src_dir.mkdir(parents=True, exist_ok=True)
    view_dir.mkdir(parents=True, exist_ok=True)

    saved_name = original_filename or source_file.name
    dest = src_dir / saved_name
    shutil.copy2(source_file, dest)

    try:
        parsed = parse_book(dest)
    except ValueError:
        shutil.rmtree(book_dir, ignore_errors=True)
        raise

    metadata_path = book_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "format": parsed.format,
                "body_chars": parsed.body_chars,
                "raw_chars": parsed.raw_chars,
                "total_paragraphs": parsed.total_paragraphs,
                "total_chapters": parsed.total_chapters,
                "total_images": parsed.total_images,
                "total_tables": parsed.total_tables,
                "total_charts": parsed.total_charts,
                "total_pages": parsed.total_pages,
                "offset_reliability": parsed.offset_reliability,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if parsed.format == "txt":
        text = dest.read_text(encoding="utf-8", errors="replace")
        cpp = parsed.chars_per_page or 1800
        pages = paginate_txt(text, cpp)
        write_pages_to_dir(view_dir, pages)
        view_path = str(view_dir)
    elif parsed.format == "docx":
        cpp = parsed.chars_per_page or 1800
        pages = paginate_docx(dest, cpp)
        write_pages_to_dir(view_dir, pages)
        view_path = str(view_dir)
    else:
        view_path = str(dest)  # pdf/epub: source file

    try:
        cur = conn.execute(
            """
            INSERT INTO book (
                slug, title, publisher_id, source_path, view_path, format,
                body_chars, raw_chars, chars_per_page, pages,
                images, charts_tables,
                audio_folder, is_draft, current_page, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'planned')
            """,
            (
                slug, title, publisher_id,
                str(dest), view_path, parsed.format,
                parsed.body_chars, parsed.raw_chars,
                parsed.chars_per_page, parsed.total_pages or 0,
                parsed.total_images, parsed.total_tables + parsed.total_charts,
                audio_folder, 1 if is_draft else 0,
            ),
        )
    except Exception:
        shutil.rmtree(book_dir, ignore_errors=True)
        raise
    return int(cur.lastrowid)
