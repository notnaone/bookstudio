from __future__ import annotations

import shutil
from pathlib import Path
from typing import Literal

RecoveryState = Literal["fresh", "restored", "live_present"]


def _is_empty(path: Path) -> bool:
    return not path.exists() or path.stat().st_size == 0


def maybe_restore_snapshot(
    live_path: Path, snapshot_path: Path
) -> RecoveryState:
    """Restore snapshot into live when live is missing or empty."""
    live_empty = _is_empty(live_path)
    snapshot_exists = snapshot_path.exists() and snapshot_path.stat().st_size > 0

    if not live_empty:
        return "live_present"

    if not snapshot_exists:
        return "fresh"

    live_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(snapshot_path, live_path)
    return "restored"


def data_root_pointer_path(local_state_dir: Path) -> Path:
    return local_state_dir / "data_root.txt"


def persist_data_root(local_state_dir: Path, data_root: Path) -> None:
    local_state_dir.mkdir(parents=True, exist_ok=True)
    data_root_pointer_path(local_state_dir).write_text(str(data_root), encoding="utf-8")


def resolve_data_root(local_state_dir: Path, live_path: Path) -> Path:
    """Resolve data_root from live DB or persisted pointer."""
    if not _is_empty(live_path):
        try:
            import sqlite3

            conn = sqlite3.connect(live_path)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT value FROM app_setting WHERE key='data_root'"
                ).fetchone()
                if row and row["value"]:
                    return Path(row["value"])
            except sqlite3.OperationalError:
                pass
            finally:
                conn.close()
        except sqlite3.Error:
            pass

    pointer = data_root_pointer_path(local_state_dir)
    if pointer.exists():
        text = pointer.read_text(encoding="utf-8").strip()
        if text:
            return Path(text)

    return local_state_dir / "tmp_data_root"
