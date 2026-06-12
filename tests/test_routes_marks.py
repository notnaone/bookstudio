from __future__ import annotations

import json
import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def _upload_book(client, tmp_path: Path, *, title: str = "Marked Book") -> dict:
    sample = tmp_path / "upload.txt"
    shutil.copy(FIXTURES / "sample.txt", sample)
    with sample.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("upload.txt", fh, "text/plain")},
            data={"title": title},
        )
    assert r.status_code == 201, r.text
    return r.json()


def _marks_json_path(data_root: Path, slug: str) -> Path:
    return data_root / "books" / slug / "marks.json"


def _load_marks_json(path: Path) -> list[dict]:
    assert path.is_file(), f"expected marks mirror at {path}"
    return json.loads(path.read_text(encoding="utf-8"))


async def test_marks_lifecycle_and_json_mirror(client, data_root: Path, tmp_path: Path):
    book = await _upload_book(client, tmp_path)
    book_id = book["id"]
    slug = book["slug"]
    marks_path = _marks_json_path(data_root, slug)

    create_payload = {
        "book_id": book_id,
        "page": 2,
        "x_pct": 10.0,
        "y_pct": 20.0,
        "w_pct": 30.0,
        "h_pct": 15.0,
        "color": "#FF0000",
        "comment": "first note",
    }
    r = await client.post("/api/marks", json=create_payload)
    assert r.status_code == 201, r.text
    created = r.json()
    mark_id = created["id"]
    assert created["book_id"] == book_id
    assert created["page"] == 2
    assert created["comment"] == "first note"
    assert created["color"] == "#FF0000"

    on_disk = _load_marks_json(marks_path)
    assert len(on_disk) == 1
    assert on_disk[0]["id"] == mark_id
    assert on_disk[0]["comment"] == "first note"

    r = await client.get(f"/api/books/{book_id}/marks")
    assert r.status_code == 200
    listed = r.json()["marks"]
    assert len(listed) == 1
    assert listed[0]["id"] == mark_id
    assert listed[0]["comment"] == "first note"

    r = await client.patch(f"/api/marks/{mark_id}", json={"comment": "updated note"})
    assert r.status_code == 200
    patched = r.json()
    assert patched["comment"] == "updated note"
    assert patched["color"] == "#FF0000"

    on_disk = _load_marks_json(marks_path)
    assert len(on_disk) == 1
    assert on_disk[0]["comment"] == "updated note"

    r = await client.delete(f"/api/marks/{mark_id}")
    assert r.status_code == 204

    on_disk = _load_marks_json(marks_path)
    assert on_disk == []

    r = await client.get(f"/api/books/{book_id}/marks")
    assert r.status_code == 200
    assert r.json()["marks"] == []


async def test_create_mark_rejects_out_of_range_x_pct(client, tmp_path: Path):
    book = await _upload_book(client, tmp_path, title="Range Check")
    r = await client.post(
        "/api/marks",
        json={
            "book_id": book["id"],
            "page": 1,
            "x_pct": 150,
            "y_pct": 10,
            "w_pct": 10,
            "h_pct": 10,
        },
    )
    assert r.status_code == 400
    assert "x_pct" in r.json()["detail"].lower()
