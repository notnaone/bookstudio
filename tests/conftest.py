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


from httpx import ASGITransport, AsyncClient

from studio_app.main import build_app


@pytest.fixture
def app(conn, data_root: Path, local_state_dir: Path):
    # Pre-seed data_root so routes that depend on it don't hit the wizard redirect.
    conn.execute(
        "INSERT INTO app_setting (key, value) VALUES ('data_root', ?)",
        (str(data_root),),
    )
    return build_app(conn=conn, data_root=data_root, local_state_dir=local_state_dir)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
