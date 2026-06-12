from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

logger = logging.getLogger(__name__)


class AudioScanner:
    """Daemon thread that runs `scan_fn(conn)` every `interval_seconds`.

    Single instance per app process. `scan_fn` is injected for testability.
    """

    def __init__(
        self,
        conn,
        interval_seconds: int,
        scan_fn: Callable[..., None],
    ):
        self._conn = conn
        self._interval = interval_seconds
        self._scan_fn = scan_fn
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_scan_at: str | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AudioScanner")
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan_fn(self._conn)
                self.last_scan_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            except Exception:
                logger.exception("AudioScanner iteration failed; will retry")
            # Sleep in small slices so stop() returns promptly.
            for _ in range(self._interval):
                if self._stop_event.wait(timeout=1.0):
                    return
