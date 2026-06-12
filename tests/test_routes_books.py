from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def test_get_books_empty(client):
    r = await client.get("/api/books")
    assert r.status_code == 200
    assert r.json() == {"books": []}


async def test_post_book_uploads_and_lists(client, tmp_path: Path):
    sample = tmp_path / "upload.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("upload.txt", fh, "text/plain")},
            data={"title": "Uploaded Book"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Uploaded Book"
    assert body["slug"] == "uploaded-book"
    assert body["body_chars"] > 0

    r2 = await client.get("/api/books")
    rows = r2.json()["books"]
    assert len(rows) == 1
    assert rows[0]["title"] == "Uploaded Book"


async def test_get_book_by_id(client, tmp_path: Path):
    sample = tmp_path / "u.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("u.txt", fh, "text/plain")},
            data={"title": "Detail Book"},
        )
    book_id = r.json()["id"]
    r2 = await client.get(f"/api/books/{book_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == book_id
    assert body["title"] == "Detail Book"


async def test_post_book_rejects_unsupported_format(client, tmp_path: Path):
    bad = tmp_path / "thing.xyz"
    bad.write_bytes(b"nope")
    with bad.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("thing.xyz", fh, "application/octet-stream")},
            data={"title": "Bad Format"},
        )
    assert r.status_code == 400
    assert "unsupported" in r.json()["detail"].lower()


async def test_get_book_404(client):
    r = await client.get("/api/books/9999")
    assert r.status_code == 404
