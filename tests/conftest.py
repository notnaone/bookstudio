from __future__ import annotations

from pathlib import Path

import pytest

from studio_app.db import connect, migrate


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data_root"
    root.mkdir()
    (root / "books").mkdir()
    (root / "exports").mkdir()
    return root


@pytest.fixture
def local_state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "local_state"
    d.mkdir()
    return d


@pytest.fixture
def conn(local_state_dir: Path):
    db = local_state_dir / "studio.live.sqlite"
    migrate(db)
    c = connect(db)
    yield c
    c.close()
