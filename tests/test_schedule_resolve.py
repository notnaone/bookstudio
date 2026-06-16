from __future__ import annotations

from studio_app.schedule_resolve import (
    auto_resolve_schedule_item,
    parse_calendar_title,
    resolve_book_for_narrator,
    resolve_narrator_from_title,
)


def test_parse_calendar_title_splits_narrator_and_book():
    assert parse_calendar_title("Chris - Foo") == ("Chris", "Foo")
    assert parse_calendar_title("Christina - Bar - Part 2") == (
        "Christina",
        "Bar - Part 2",
    )
    assert parse_calendar_title("Studio booking") == (None, None)


def test_resolve_narrator_from_title_uses_alias_prefix(conn):
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    )
    assert resolve_narrator_from_title(conn, "Chris - Foo") == 1
    assert resolve_narrator_from_title(conn, "Studio booking") is None


def test_resolve_narrator_longest_alias_wins(conn):
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    )
    conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Christina', 'Christina')"
    )
    assert resolve_narrator_from_title(conn, "Christina - Bar") == 2


def test_resolve_book_for_narrator_matches_title(conn):
    narr = conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    ).lastrowid
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, narrator_id, status)"
        " VALUES ('foo', 'Foo', 'txt', '/x', '/x', ?, 'in_progress')",
        (narr,),
    ).lastrowid
    assert resolve_book_for_narrator(conn, narr, "Foo") == book_id
    assert resolve_book_for_narrator(conn, narr, "Unknown") is None


def test_auto_resolve_schedule_item_sets_narrator_and_book(conn):
    narr = conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    ).lastrowid
    book_id = conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, narrator_id, status)"
        " VALUES ('foo', 'Foo', 'txt', '/x', '/x', ?, 'in_progress')",
        (narr,),
    ).lastrowid
    item_id = conn.execute(
        "INSERT INTO schedule_item"
        " (source, google_event_id, start_time, end_time, raw_title, action_status)"
        " VALUES ('studio_1', 'uid-1', '2026-06-21T10:00:00+00:00',"
        " '2026-06-21T12:00:00+00:00', 'Chris - Foo', 'pending')"
    ).lastrowid

    auto_resolve_schedule_item(conn, item_id, "Chris - Foo")

    row = conn.execute(
        "SELECT resolved_narrator_id, resolved_book_id, action_status, resolved_at"
        " FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    assert row["resolved_narrator_id"] == narr
    assert row["resolved_book_id"] == book_id
    assert row["action_status"] == "pending"
    assert row["resolved_at"] is not None


def test_auto_resolve_does_not_overwrite_existing(conn):
    narr = conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    ).lastrowid
    other = conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Alex', 'Alex')"
    ).lastrowid
    item_id = conn.execute(
        "INSERT INTO schedule_item"
        " (source, google_event_id, start_time, end_time, raw_title,"
        " resolved_narrator_id, action_status)"
        " VALUES ('studio_1', 'uid-2', '2026-06-21T10:00:00+00:00',"
        " '2026-06-21T12:00:00+00:00', 'Chris - Foo', ?, 'pending')",
        (other,),
    ).lastrowid

    auto_resolve_schedule_item(conn, item_id, "Chris - Foo")

    row = conn.execute(
        "SELECT resolved_narrator_id FROM schedule_item WHERE id = ?",
        (item_id,),
    ).fetchone()
    assert row["resolved_narrator_id"] == other
