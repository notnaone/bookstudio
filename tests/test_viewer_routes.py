from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def _upload(client, tmp_path, title="X"):
    s = tmp_path / "x.txt"
    shutil.copy(FIXTURES / "sample.txt", s)
    with s.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("x.txt", fh, "text/plain")},
            data={"title": title},
        )
    return r.json()["id"]


async def test_view_page_returns_html(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.get(f"/api/books/{bid}/view/page-0001.html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


async def test_view_page_404_missing(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.get(f"/api/books/{bid}/view/page-9999.html")
    assert r.status_code == 404


async def test_view_source_returns_file(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.get(f"/api/books/{bid}/view/source")
    assert r.status_code == 200
