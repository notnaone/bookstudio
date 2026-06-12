from __future__ import annotations

import threading
import time

from studio_app.background import AudioScanner


def test_audio_scanner_runs_once_immediately(conn):
    calls = []
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: calls.append(c))
    scanner.start()
    time.sleep(0.2)
    scanner.stop()
    assert len(calls) >= 1


def test_audio_scanner_stop_is_idempotent(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    scanner.stop()
    scanner.stop()  # must not raise


def test_audio_scanner_thread_is_daemon(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    assert scanner._thread is not None and scanner._thread.daemon
    scanner.stop()


def test_audio_scanner_records_last_scan_at(conn):
    scanner = AudioScanner(conn, interval_seconds=60, scan_fn=lambda c: None)
    scanner.start()
    time.sleep(0.2)
    scanner.stop()
    assert scanner.last_scan_at is not None
