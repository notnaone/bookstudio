from __future__ import annotations

from pathlib import Path

from studio_app.db import connect, migrate
from studio_app.recovery import (
    maybe_restore_snapshot,
    persist_data_root,
    resolve_data_root,
)


def _make_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    data_root.mkdir()
    live = tmp_path / "local" / "studio.live.sqlite"
    snap = data_root / "studio.sqlite"
    migrate(live)
    conn = connect(live)
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('data_root', ?)",
        (str(data_root),),
    )
    conn.execute("INSERT INTO publisher (name) VALUES ('Recovered')")
    conn.close()
    snap.parent.mkdir(parents=True, exist_ok=True)
    snap.write_bytes(live.read_bytes())
    return live, snap


def test_maybe_restore_fresh_when_both_missing(tmp_path: Path):
    live = tmp_path / "studio.live.sqlite"
    snap = tmp_path / "studio.sqlite"
    assert maybe_restore_snapshot(live, snap) == "fresh"


def test_maybe_restore_live_present(tmp_path: Path):
    live, snap = _make_snapshot(tmp_path)
    assert maybe_restore_snapshot(live, snap) == "live_present"
    assert snap.exists()


def test_maybe_restore_from_snapshot(tmp_path: Path):
    live, snap = _make_snapshot(tmp_path)
    live.unlink()
    assert maybe_restore_snapshot(live, snap) == "restored"
    assert live.exists()
    conn = connect(live)
    row = conn.execute(
        "SELECT name FROM publisher WHERE name = 'Recovered'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_maybe_restore_empty_live(tmp_path: Path):
    live, snap = _make_snapshot(tmp_path)
    live.write_bytes(b"")
    assert maybe_restore_snapshot(live, snap) == "restored"
    assert live.stat().st_size > 0


def test_resolve_data_root_from_pointer(tmp_path: Path):
    local = tmp_path / "local"
    local.mkdir()
    data_root = tmp_path / "drive" / "Studio"
    persist_data_root(local, data_root)
    resolved = resolve_data_root(local, local / "studio.live.sqlite")
    assert resolved == data_root
