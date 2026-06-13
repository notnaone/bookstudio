from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from studio_app.db_lock import hold

logger = logging.getLogger(__name__)


def snapshot_now(live_path: Path, snapshot_path: Path) -> int:
    """Checkpoint WAL, online-backup to .tmp, atomic rename. Returns bytes written."""
    if not live_path.exists():
        raise FileNotFoundError(live_path)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = snapshot_path.with_name(snapshot_path.name + ".tmp")
    if tmp_path.exists():
        tmp_path.unlink()

    live = sqlite3.connect(live_path)
    try:
        live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dest = sqlite3.connect(tmp_path)
        try:
            live.backup(dest)
        finally:
            dest.close()
    finally:
        live.close()

    tmp_path.replace(snapshot_path)
    return snapshot_path.stat().st_size


class SnapshotJob:
    """Daemon thread that snapshots the live DB on an interval."""

    def __init__(
        self,
        live_path: Path,
        snapshot_path: Path,
        interval_seconds: int,
        snapshot_fn: Callable[[Path, Path], int] | None = None,
        db_lock: threading.Lock | None = None,
    ):
        self._live_path = live_path
        self._snapshot_path = snapshot_path
        self._interval = interval_seconds
        self._snapshot_fn = snapshot_fn or snapshot_now
        self._db_lock = db_lock
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_snapshot_at: str | None = None
        self.last_snapshot_bytes: int | None = None

    def run_once(self) -> int:
        if not self._live_path.exists():
            return 0
        if self._db_lock is not None:
            with hold(self._db_lock):
                nbytes = self._snapshot_fn(self._live_path, self._snapshot_path)
        else:
            nbytes = self._snapshot_fn(self._live_path, self._snapshot_path)
        self.last_snapshot_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.last_snapshot_bytes = nbytes
        return nbytes

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="SnapshotJob"
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
                self.run_once()
            except FileNotFoundError:
                pass
            except Exception:
                logger.exception("SnapshotJob iteration failed; will retry")
            for _ in range(self._interval):
                if self._stop_event.wait(timeout=1.0):
                    return
