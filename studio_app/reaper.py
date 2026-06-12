from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)


def reap_stale_sessions(conn: sqlite3.Connection, idle_timeout_seconds: int) -> None:
    """Close open reading sessions idle longer than `idle_timeout_seconds`."""
    modifier = f"-{idle_timeout_seconds} seconds"
    conn.execute(
        """
        UPDATE reading_session
           SET ended_at = COALESCE(last_heartbeat_at, started_at),
               end_page = tracked_progress_page,
               auto_closed = 1
         WHERE ended_at IS NULL
           AND (
             last_heartbeat_at IS NULL
             OR julianday(last_heartbeat_at) < julianday('now', ?)
           )
        """,
        (modifier,),
    )


class SessionReaper:
    """Daemon thread that runs `reap_fn(conn)` every `interval_seconds`.

    Single instance per app process. `reap_fn` is injected for testability.
    """

    def __init__(
        self,
        conn,
        idle_timeout_seconds: int,
        interval_seconds: int,
        reap_fn: Callable[..., None] | None = None,
    ):
        self._conn = conn
        self._idle_timeout_seconds = idle_timeout_seconds
        self._interval = interval_seconds
        self._reap_fn = reap_fn or (
            lambda c: reap_stale_sessions(c, self._idle_timeout_seconds)
        )
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_run_at: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="SessionReaper"
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
                self._reap_fn(self._conn)
                self.last_run_at = datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                )
            except Exception:
                logger.exception("SessionReaper iteration failed; will retry")
            for _ in range(self._interval):
                if self._stop_event.wait(timeout=1.0):
                    return
