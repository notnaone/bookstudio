"""Resolve schedule items to narrators and books from calendar event titles."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_calendar_title(raw_title: str) -> tuple[str | None, str | None]:
    """Split 'Narrator - Book' or return a single narrator-only title."""
    title = (raw_title or "").strip()
    if not title:
        return None, None
    if " - " in title:
        left, right = title.split(" - ", 1)
        narrator_part = left.strip() or None
        book_part = right.strip() or None
        return narrator_part, book_part
    return title, None


def resolve_narrator_from_title(conn: sqlite3.Connection, raw_title: str) -> int | None:
    """Match narrator by calendar_alias prefix or by name."""
    narrator_id = _match_narrator_alias(conn, raw_title)
    if narrator_id is not None:
        return narrator_id
    narrator_part, _ = parse_calendar_title(raw_title)
    if narrator_part:
        narrator_id = _match_narrator_name(conn, narrator_part)
        if narrator_id is not None:
            return narrator_id
        return _match_narrator_alias(conn, narrator_part)
    return None


def _match_narrator_name(conn: sqlite3.Connection, text: str) -> int | None:
    text = text.strip()
    if not text:
        return None
    row = conn.execute(
        "SELECT id FROM narrator WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) LIMIT 1",
        (text,),
    ).fetchone()
    if row:
        return int(row["id"])
    row = conn.execute(
        "SELECT id FROM narrator"
        " WHERE LOWER(?) LIKE LOWER(TRIM(name)) || '%'"
        " ORDER BY LENGTH(name) DESC"
        " LIMIT 1",
        (text,),
    ).fetchone()
    return int(row["id"]) if row else None


def _match_narrator_alias(conn: sqlite3.Connection, text: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM narrator"
        " WHERE calendar_alias IS NOT NULL"
        " AND LOWER(?) LIKE LOWER(calendar_alias) || '%'"
        " ORDER BY LENGTH(calendar_alias) DESC"
        " LIMIT 1",
        (text,),
    ).fetchone()
    return int(row["id"]) if row else None


def resolve_book_for_narrator(
    conn: sqlite3.Connection,
    narrator_id: int,
    book_title_hint: str,
) -> int | None:
    """Find an in-progress book for a narrator matching a title hint."""
    hint = book_title_hint.strip()
    if not hint:
        return None
    row = conn.execute(
        "SELECT id FROM book"
        " WHERE narrator_id = ? AND status = 'in_progress'"
        " AND LOWER(TRIM(title)) = LOWER(TRIM(?))"
        " LIMIT 1",
        (narrator_id, hint),
    ).fetchone()
    if row:
        return int(row["id"])
    row = conn.execute(
        "SELECT id FROM book"
        " WHERE narrator_id = ? AND status = 'in_progress'"
        " AND (LOWER(title) LIKE '%' || LOWER(?) || '%'"
        " OR LOWER(?) LIKE '%' || LOWER(title) || '%')"
        " ORDER BY LENGTH(title)"
        " LIMIT 1",
        (narrator_id, hint, hint),
    ).fetchone()
    return int(row["id"]) if row else None


def auto_resolve_schedule_item(
    conn: sqlite3.Connection,
    item_id: int,
    raw_title: str,
) -> None:
    """Set resolved narrator/book when still unset; never changes action_status."""
    row = conn.execute(
        "SELECT resolved_narrator_id, resolved_book_id"
        " FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        return

    updates: dict[str, object] = {}
    narrator_id = row["resolved_narrator_id"]
    book_id = row["resolved_book_id"]

    if narrator_id is None:
        narrator_id = resolve_narrator_from_title(conn, raw_title)
        if narrator_id is not None:
            updates["resolved_narrator_id"] = narrator_id

    if book_id is None and narrator_id is not None:
        _, book_part = parse_calendar_title(raw_title)
        if book_part:
            matched = resolve_book_for_narrator(conn, narrator_id, book_part)
            if matched is not None:
                updates["resolved_book_id"] = matched

    if not updates:
        return

    updates["resolved_at"] = _utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE schedule_item SET {set_clause} WHERE id = ?",
        (*updates.values(), item_id),
    )
