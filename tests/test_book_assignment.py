from __future__ import annotations

import shutil
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


async def _create_book(client, tmp_path, title="A"):
    s = tmp_path / "x.txt"
    shutil.copy(FIXTURES / "sample.txt", s)
    with s.open("rb") as fh:
        r = await client.post(
            "/api/books",
            files={"file": ("x.txt", fh, "text/plain")},
            data={"title": title},
        )
    return r.json()["id"]


async def test_assigning_narrator_creates_history_row(client, conn, tmp_path: Path):
    n = await client.post("/api/narrators", json={"name": "Alice"})
    nid = n.json()["id"]
    bid = await _create_book(client, tmp_path)
    await client.patch(f"/api/books/{bid}", json={"narrator_id": nid})

    rows = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ? AND narrator_id = ?",
        (bid, nid),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["finished_at"] is None


async def test_reassigning_narrator_closes_previous_history(client, conn, tmp_path: Path):
    n1 = (await client.post("/api/narrators", json={"name": "Alice"})).json()["id"]
    n2 = (await client.post("/api/narrators", json={"name": "Bob"})).json()["id"]
    bid = await _create_book(client, tmp_path)
    await client.patch(f"/api/books/{bid}", json={"narrator_id": n1})
    await client.patch(f"/api/books/{bid}", json={"narrator_id": n2})

    alice = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ? AND narrator_id = ?",
        (bid, n1),
    ).fetchone()
    bob = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ? AND narrator_id = ?",
        (bid, n2),
    ).fetchone()
    assert alice["finished_at"] is not None
    assert bob["finished_at"] is None


async def test_marking_book_done_sets_finished_at(client, conn, tmp_path: Path):
    nid = (await client.post("/api/narrators", json={"name": "Done Narr"})).json()["id"]
    bid = await _create_book(client, tmp_path)
    await client.patch(f"/api/books/{bid}", json={"narrator_id": nid})
    await client.patch(f"/api/books/{bid}", json={"status": "done"})

    row = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ? AND narrator_id = ?",
        (bid, nid),
    ).fetchone()
    assert row["finished_at"] is not None


async def test_unassigning_narrator_closes_history(client, conn, tmp_path: Path):
    nid = (await client.post("/api/narrators", json={"name": "C"})).json()["id"]
    bid = await _create_book(client, tmp_path)
    await client.patch(f"/api/books/{bid}", json={"narrator_id": nid})
    await client.patch(f"/api/books/{bid}", json={"narrator_id": None})

    row = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ?", (bid,)
    ).fetchone()
    assert row["finished_at"] is not None
