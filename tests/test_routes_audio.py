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


async def test_get_book_includes_stats_block(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.get(f"/api/books/{bid}")
    assert r.status_code == 200
    body = r.json()
    assert "stats" in body
    assert body["stats"]["total_audio_seconds"] == 0


async def test_rescan_audio_with_no_folder_returns_zero(client, tmp_path):
    bid = await _upload(client, tmp_path)
    r = await client.post(f"/api/books/{bid}/rescan_audio")
    assert r.status_code == 200
    assert r.json() == {"book_id": bid, "audio_files": 0}


async def test_rescan_audio_with_mp3_returns_count(client, tmp_path):
    bid = await _upload(client, tmp_path)
    af = tmp_path / "audio"
    af.mkdir()
    shutil.copy(FIXTURES / "silence.mp3", af / "ch.mp3")
    await client.patch(f"/api/books/{bid}", json={"audio_folder": str(af)})
    r = await client.post(f"/api/books/{bid}/rescan_audio")
    body = r.json()
    assert body["audio_files"] == 1
    r2 = await client.get(f"/api/books/{bid}")
    assert r2.json()["stats"]["total_audio_seconds"] > 0


async def test_rescan_audio_404(client):
    r = await client.post("/api/books/9999/rescan_audio")
    assert r.status_code == 404
