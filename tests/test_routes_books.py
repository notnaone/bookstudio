from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

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


@patch("studio_app.routes.books.download_source")
async def test_post_book_from_url(mock_download, client, tmp_path: Path):
    sample = tmp_path / "remote.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    mock_download.return_value = sample

    r = await client.post(
        "/api/books/from_url",
        json={
            "title": "Drive Book",
            "url": "https://drive.google.com/file/d/abc/view",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Drive Book"
    assert body["format"] == "txt"
    mock_download.assert_called_once()


async def test_post_book_preserves_original_filename(client, tmp_path: Path):
    sample = tmp_path / "internal_tmp_path.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("Publisher Sent This.txt", fh, "text/plain")},
            data={"title": "Filename Check"},
        )
    assert r.status_code == 201
    src_path = r.json()["source_path"]
    assert src_path.endswith("Publisher Sent This.txt"), src_path
    assert "internal_tmp_path" not in src_path


async def test_post_book_large_payload_streamed(client, tmp_path: Path):
    """Upload ~1 MB TXT to exercise the chunked read loop (>1 KB chunks)."""
    big = tmp_path / "big.txt"
    big.write_text("paragraph " * 100_000, encoding="utf-8")  # ~1 MB
    with big.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("BigBook.txt", fh, "text/plain")},
            data={"title": "Big Upload"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    # parser counts non-whitespace chars; "paragraph" is 9 chars, x 100k = 900k
    assert body["body_chars"] > 500_000


async def _create_test_book(client, tmp_path, title="Edit Me"):
    sample = tmp_path / "patch.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("patch.txt", fh, "text/plain")},
            data={"title": title},
        )
    return r.json()["id"]


async def test_patch_book_updates_status(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(f"/api/books/{bid}", json={"status": "in_progress"})
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


async def test_patch_book_rejects_invalid_status(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(f"/api/books/{bid}", json={"status": "nope"})
    assert r.status_code == 400


async def test_patch_book_updates_metadata_fields(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(
        f"/api/books/{bid}",
        json={
            "genre": "Sci-Fi",
            "publisher_notes": "delivered 2026-05",
            "planned_end": "2026-07-15",
        },
    )
    body = r.json()
    assert body["genre"] == "Sci-Fi"
    assert body["publisher_notes"] == "delivered 2026-05"
    assert body["planned_end"] == "2026-07-15"


async def test_patch_book_rejects_unknown_field(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(f"/api/books/{bid}", json={"slug": "hijack"})
    assert r.status_code == 400


async def test_patch_book_404(client):
    r = await client.patch("/api/books/9999", json={"status": "done"})
    assert r.status_code == 404


async def test_patch_book_clear_draft_requires_publisher_and_genre(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    # Force into draft state first.
    r = await client.patch(f"/api/books/{bid}", json={"is_draft": True})
    assert r.status_code == 200 and r.json()["is_draft"] == 1
    # Now refuse to clear with missing required fields.
    r = await client.patch(f"/api/books/{bid}", json={"is_draft": False})
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "publisher" in detail or "genre" in detail


async def test_list_books_filters_by_status(client, tmp_path: Path):
    b1 = await _create_test_book(client, tmp_path, title="Planned One")
    b2 = await _create_test_book(client, tmp_path, title="In Progress One")
    await client.patch(f"/api/books/{b2}", json={"status": "in_progress"})

    r = await client.get("/api/books?status=in_progress")
    titles = [b["title"] for b in r.json()["books"]]
    assert titles == ["In Progress One"]


async def test_list_books_filters_by_title_substring(client, tmp_path: Path):
    await _create_test_book(client, tmp_path, title="Alpha Book")
    await _create_test_book(client, tmp_path, title="Beta Book")
    r = await client.get("/api/books?q=alpha")
    titles = [b["title"] for b in r.json()["books"]]
    assert titles == ["Alpha Book"]


async def test_patch_book_invalid_narrator_id_returns_400(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path, title="FK Check")
    r = await client.patch(f"/api/books/{bid}", json={"narrator_id": 9999})
    assert r.status_code == 400
    assert "foreign key" in r.json()["detail"].lower()


async def test_patch_book_invalid_publisher_id_returns_400(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path, title="FK Check P")
    r = await client.patch(f"/api/books/{bid}", json={"publisher_id": 9999})
    assert r.status_code == 400


async def test_list_books_filters_by_narrator(client, tmp_path: Path):
    n = await client.post("/api/narrators", json={"name": "Filter Narr"})
    nid = n.json()["id"]
    b1 = await _create_test_book(client, tmp_path, title="Assigned")
    b2 = await _create_test_book(client, tmp_path, title="Unassigned")
    await client.patch(f"/api/books/{b1}", json={"narrator_id": nid})
    r = await client.get(f"/api/books?narrator_id={nid}")
    titles = [b["title"] for b in r.json()["books"]]
    assert titles == ["Assigned"]


async def test_patch_active_page_updates_current_page(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(
        f"/api/books/{bid}/active_page", json={"tracked_progress_page": 1}
    )
    assert r.status_code == 200
    assert r.json()["current_page"] == 1


async def test_patch_active_page_404(client):
    r = await client.patch(
        "/api/books/9999/active_page", json={"tracked_progress_page": 1}
    )
    assert r.status_code == 404


async def test_patch_active_page_rejects_invalid(client, tmp_path: Path):
    bid = await _create_test_book(client, tmp_path)
    r = await client.patch(
        f"/api/books/{bid}/active_page", json={"tracked_progress_page": 0}
    )
    assert r.status_code == 400
