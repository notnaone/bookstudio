from __future__ import annotations

from pathlib import Path

import pytest

from studio_app.db import connect, migrate
from studio_app.snapshot import SnapshotJob, snapshot_now


def _seed_live(tmp_path: Path) -> Path:
    live = tmp_path / "studio.live.sqlite"
    migrate(live)
    conn = connect(live)
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('data_root', ?)",
        (str(tmp_path / "data"),),
    )
    conn.execute(
        "INSERT INTO publisher (name) VALUES ('Snapshot Pub')"
    )
    conn.close()
    return live


def test_snapshot_now_copies_data(tmp_path: Path):
    live = _seed_live(tmp_path)
    snap = tmp_path / "data" / "studio.sqlite"

    nbytes = snapshot_now(live, snap)
    assert nbytes > 0
    assert snap.is_file()

    snap_conn = connect(snap)
    row = snap_conn.execute(
        "SELECT name FROM publisher WHERE name = 'Snapshot Pub'"
    ).fetchone()
    snap_conn.close()
    assert row is not None


def test_snapshot_now_overwrites_stale_tmp(tmp_path: Path):
    live = _seed_live(tmp_path)
    snap = tmp_path / "data" / "studio.sqlite"
    stale_tmp = snap.with_name(snap.name + ".tmp")
    stale_tmp.parent.mkdir(parents=True, exist_ok=True)
    stale_tmp.write_bytes(b"stale partial write")

    snapshot_now(live, snap)
    assert snap.is_file()
    assert not stale_tmp.exists()


def test_snapshot_job_runs_periodically(tmp_path: Path):
    live = _seed_live(tmp_path)
    snap = tmp_path / "data" / "studio.sqlite"
    job = SnapshotJob(live, snap, interval_seconds=1)
    job.start()
    try:
        for _ in range(30):
            if snap.exists():
                break
            __import__("time").sleep(0.1)
        assert snap.exists()
        assert job.last_snapshot_at is not None
        assert job.last_snapshot_bytes is not None
    finally:
        job.stop()


def test_snapshot_job_skips_missing_live(tmp_path: Path):
    live = tmp_path / "missing.live.sqlite"
    snap = tmp_path / "studio.sqlite"
    job = SnapshotJob(live, snap, interval_seconds=1)
    assert job.run_once() == 0
