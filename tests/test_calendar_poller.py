from __future__ import annotations

from pathlib import Path

from studio_app.calendar_poller import CalendarPoller, poll_calendars, sync_calendar_source
from studio_app.ics_client import parse_ics

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"
CHRIS_UID = "evt-chris-foo@bookstudio.test"
CHRISTINA_UID = "evt-christina-bar@bookstudio.test"
BOOKING_UID = "evt-studio-booking@bookstudio.test"


def test_sync_calendar_source_auto_resolves_narrator_and_book(conn):
    narr = conn.execute(
        "INSERT INTO narrator (name, calendar_alias) VALUES ('Chris', 'Chris')"
    ).lastrowid
    conn.execute(
        "INSERT INTO book (slug, title, format, source_path, view_path, narrator_id, status)"
        " VALUES ('foo', 'Foo', 'txt', '/x', '/x', ?, 'in_progress')",
        (narr,),
    )

    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)

    row = conn.execute(
        "SELECT raw_title, resolved_narrator_id, resolved_book_id, resolved_at"
        " FROM schedule_item WHERE google_event_id = ?",
        (CHRIS_UID,),
    ).fetchone()
    assert row["raw_title"] == "Chris - Foo"
    assert row["resolved_narrator_id"] == narr
    assert row["resolved_book_id"] is not None
    assert row["resolved_at"] is not None


def test_sync_calendar_source_inserts_fixture_events(conn):
    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)

    rows = conn.execute(
        "SELECT google_event_id, raw_title, source, action_status"
        " FROM schedule_item WHERE source = 'studio_1'"
        " ORDER BY start_time"
    ).fetchall()
    assert len(rows) == 3
    assert rows[0]["google_event_id"] == CHRIS_UID
    assert rows[0]["raw_title"] == "Chris - Foo"
    assert rows[0]["action_status"] == "pending"
    assert rows[1]["google_event_id"] == CHRISTINA_UID
    assert rows[2]["google_event_id"] == BOOKING_UID


def test_sync_calendar_source_cancels_missing_uid(conn):
    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)

    reduced = [e for e in events if e.uid != CHRIS_UID]
    sync_calendar_source(conn, "studio_1", reduced)

    chris = conn.execute(
        "SELECT action_status FROM schedule_item WHERE google_event_id = ?",
        (CHRIS_UID,),
    ).fetchone()
    assert chris["action_status"] == "cancelled"

    christina = conn.execute(
        "SELECT action_status FROM schedule_item WHERE google_event_id = ?",
        (CHRISTINA_UID,),
    ).fetchone()
    assert christina["action_status"] == "pending"


def test_sync_calendar_source_does_not_cancel_started_rows(conn):
    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)
    conn.execute(
        "UPDATE schedule_item SET action_status = 'started' WHERE google_event_id = ?",
        (CHRIS_UID,),
    )

    sync_calendar_source(conn, "studio_1", [])

    chris = conn.execute(
        "SELECT action_status FROM schedule_item WHERE google_event_id = ?",
        (CHRIS_UID,),
    ).fetchone()
    assert chris["action_status"] == "started"


def test_sync_calendar_source_leaves_manual_rows_untouched(conn):
    manual_id = conn.execute(
        "INSERT INTO schedule_item"
        " (source, start_time, end_time, raw_title, kind, action_status)"
        " VALUES ('manual', '2026-06-20T09:00:00+00:00',"
        " '2026-06-20T11:00:00+00:00', 'Manual block', 'deadline', 'pending')"
    ).lastrowid

    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)

    manual = conn.execute(
        "SELECT source, action_status, raw_title FROM schedule_item WHERE id = ?",
        (manual_id,),
    ).fetchone()
    assert manual["source"] == "manual"
    assert manual["action_status"] == "pending"
    assert manual["raw_title"] == "Manual block"


def test_sync_calendar_source_does_not_reset_action_status_on_update(conn):
    events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", events)
    conn.execute(
        "UPDATE schedule_item SET action_status = 'started' WHERE google_event_id = ?",
        (CHRISTINA_UID,),
    )

    updated_events = parse_ics(FIXTURE.read_bytes())
    sync_calendar_source(conn, "studio_1", updated_events)

    row = conn.execute(
        "SELECT action_status, raw_title FROM schedule_item WHERE google_event_id = ?",
        (CHRISTINA_UID,),
    ).fetchone()
    assert row["action_status"] == "started"
    assert row["raw_title"] == "Christina - Bar"


def test_poll_calendars_uses_fetch_fn_per_source(conn):
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        return FIXTURE.read_bytes()

    poll_calendars(
        conn,
        fetch_fn=fetch,
        urls={"studio_1": "http://studio-1.test/feed.ics", "studio_2": None},
    )

    assert calls == ["http://studio-1.test/feed.ics"]
    assert conn.execute("SELECT COUNT(*) AS n FROM schedule_item").fetchone()["n"] == 3


def test_calendar_poller_poll_once_sets_last_sync_at(conn):
    poller = CalendarPoller(
        conn,
        interval_seconds=60,
        fetch_fn=lambda url: FIXTURE.read_bytes(),
        urls_provider=lambda c: {"studio_1": "http://example.test/ics", "studio_2": None},
    )
    assert poller.last_sync_at is None
    poller.poll_once()
    assert poller.last_sync_at is not None
