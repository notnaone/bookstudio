from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable

from studio_app.ics_client import CalendarEvent, parse_ics

logger = logging.getLogger(__name__)

FetchFn = Callable[[str], bytes]
UrlsProvider = Callable[[sqlite3.Connection], dict[str, str | None]]
SyncFn = Callable[[sqlite3.Connection, str, list[CalendarEvent]], None]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dt_iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def sync_calendar_source(
    conn: sqlite3.Connection,
    source: str,
    events: list[CalendarEvent],
) -> None:
    """Upsert calendar events for one studio source and cancel missing UIDs."""
    seen_uids: set[str] = set()
    now = _utc_now()

    for event in events:
        seen_uids.add(event.uid)
        start_time = _dt_iso(event.dtstart)
        end_time = _dt_iso(event.dtend)
        existing = conn.execute(
            "SELECT id FROM schedule_item WHERE google_event_id = ?",
            (event.uid,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO schedule_item"
                " (source, google_event_id, start_time, end_time, raw_title, notes,"
                " last_synced_at, action_status)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')",
                (
                    source,
                    event.uid,
                    start_time,
                    end_time,
                    event.summary,
                    event.description,
                    now,
                ),
            )
        else:
            conn.execute(
                "UPDATE schedule_item"
                " SET start_time = ?, end_time = ?, raw_title = ?, notes = ?,"
                " last_synced_at = ?"
                " WHERE id = ?",
                (
                    start_time,
                    end_time,
                    event.summary,
                    event.description,
                    now,
                    existing["id"],
                ),
            )

    if seen_uids:
        placeholders = ", ".join("?" * len(seen_uids))
        conn.execute(
            f"UPDATE schedule_item SET action_status = 'cancelled'"
            f" WHERE source = ?"
            f" AND google_event_id IS NOT NULL"
            f" AND action_status = 'pending'"
            f" AND google_event_id NOT IN ({placeholders})",
            (source, *sorted(seen_uids)),
        )
    else:
        conn.execute(
            "UPDATE schedule_item SET action_status = 'cancelled'"
            " WHERE source = ? AND google_event_id IS NOT NULL"
            " AND action_status = 'pending'",
            (source,),
        )


def poll_calendars(
    conn: sqlite3.Connection,
    *,
    fetch_fn: FetchFn,
    urls: dict[str, str | None],
    sync_fn: SyncFn | None = None,
) -> None:
    """Fetch each configured ICS URL and sync events into schedule_item."""
    sync = sync_fn or sync_calendar_source
    for source in ("studio_1", "studio_2"):
        url = urls.get(source)
        if not url:
            continue
        ics_bytes = fetch_fn(url)
        events = parse_ics(ics_bytes)
        sync(conn, source, events)


class CalendarPoller:
    """Daemon thread that polls ICS feeds on an interval."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        interval_seconds: int,
        fetch_fn: FetchFn,
        urls_provider: UrlsProvider,
        sync_fn: SyncFn | None = None,
        poll_fn: Callable[..., None] | None = None,
    ):
        self._conn = conn
        self._interval = interval_seconds
        self._fetch_fn = fetch_fn
        self._urls_provider = urls_provider
        self._sync_fn = sync_fn
        self._poll_fn = poll_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_sync_at: str | None = None

    def poll_once(self) -> None:
        if self._poll_fn is not None:
            self._poll_fn()
        else:
            poll_calendars(
                self._conn,
                fetch_fn=self._fetch_fn,
                urls=self._urls_provider(self._conn),
                sync_fn=self._sync_fn,
            )
        self.last_sync_at = _utc_now()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="CalendarPoller"
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                logger.exception("CalendarPoller iteration failed; will retry")
            for _ in range(self._interval):
                if self._stop_event.wait(timeout=1.0):
                    return
