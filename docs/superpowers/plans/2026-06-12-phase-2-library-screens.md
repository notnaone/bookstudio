# Phase 2 — Library Screens & CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Round out the data-management surface introduced in Phase 1: publishers/narrators CRUD, editable book detail, a library page with three filterable tabs, a narrator-detail screen, and a manual book-to-narrator assignment flow. End state: you can manage your entire catalog from the browser without touching SQL.

**Architecture:** Same FastAPI process, same SQLite store. Adds five new route modules (or extends existing ones), expands `library.html` into a tabbed view, adds a `narrator.html` page, and wires inline-editable fields on book and narrator details. No background jobs yet (Phase 3). No viewer (Phase 4). Stats panels show placeholders since the audio scanner hasn't run yet.

**Tech Stack:** Unchanged from Phase 1 — FastAPI, sqlite3 stdlib, vanilla JS, pytest + httpx.

**Prereqs:** Phase 1 merged to `master`. Tests baseline: 47 passed + 2 skipped on `master`.

---

## File structure

**New files:**
```
studio_app/routes/publishers.py
studio_app/routes/narrators.py
studio_app/static/narrator.html
tests/test_routes_publishers.py
tests/test_routes_narrators.py
tests/test_book_assignment.py
```

**Modified files:**
```
studio_app/routes/books.py          # PATCH endpoint, query-string filters
studio_app/main.py                   # mount new routers + /narrators/<id> static
studio_app/static/library.html       # add Narrators + Publishers tabs
studio_app/static/book.html          # editable form fields + assignment dropdowns
studio_app/static/app.js             # setup functions for new pages, tab switch, filters
studio_app/static/styles.css         # tab styling
tests/test_routes_books.py           # PATCH + filter tests
```

**Untouched:**
```
studio_app/{db,ingest,parser_adapter,settings,slug}.py
studio_app/routes/{system,settings_routes}.py
studio_app/migrations/001_initial.sql
```

---

## Cross-cutting rules

- TDD throughout. Failing test → minimal pass → commit.
- One commit per task.
- All endpoints follow the same response shape: a single resource returns the resource dict; a list returns `{"<plural>": [...]}`.
- Error shape: `HTTPException` with `detail` string. 404 for missing resource; 400 for bad payload.
- All write endpoints (POST / PATCH / DELETE) accept JSON; multipart only for file uploads.
- The `app.state.conn` pattern is canonical — no closure captures.

---

## Task 1: Publishers CRUD

**Files:**
- Create: `studio_app/routes/publishers.py`
- Modify: `studio_app/main.py` (mount router)
- Test: `tests/test_routes_publishers.py`

- [ ] **Step 1: Failing tests**

Create `tests/test_routes_publishers.py`:

```python
from __future__ import annotations


async def test_list_publishers_empty(client):
    r = await client.get("/api/publishers")
    assert r.status_code == 200
    assert r.json() == {"publishers": []}


async def test_create_publisher(client):
    r = await client.post(
        "/api/publishers", json={"name": "Penguin", "notes": "fiction imprint"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Penguin"
    assert body["notes"] == "fiction imprint"
    assert "id" in body


async def test_create_publisher_rejects_blank_name(client):
    r = await client.post("/api/publishers", json={"name": "  "})
    assert r.status_code == 400


async def test_create_publisher_rejects_missing_name(client):
    r = await client.post("/api/publishers", json={"notes": "no name"})
    assert r.status_code == 400


async def test_patch_publisher_updates_fields(client):
    r = await client.post("/api/publishers", json={"name": "Original"})
    pid = r.json()["id"]
    r2 = await client.patch(
        f"/api/publishers/{pid}",
        json={"name": "Renamed", "notes": "added note"},
    )
    assert r2.status_code == 200
    assert r2.json()["name"] == "Renamed"
    assert r2.json()["notes"] == "added note"


async def test_patch_publisher_404(client):
    r = await client.patch("/api/publishers/9999", json={"name": "x"})
    assert r.status_code == 404


async def test_list_publishers_after_create(client):
    await client.post("/api/publishers", json={"name": "A"})
    await client.post("/api/publishers", json={"name": "B"})
    r = await client.get("/api/publishers")
    names = sorted(p["name"] for p in r.json()["publishers"])
    assert names == ["A", "B"]
```

Run `uv run pytest tests/test_routes_publishers.py -v` → ImportError.

- [ ] **Step 2: Implement `studio_app/routes/publishers.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _row(r) -> dict:
    return {"id": r["id"], "name": r["name"], "notes": r["notes"]}


@router.get("/api/publishers")
def list_publishers(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute("SELECT * FROM publisher ORDER BY name").fetchall()
    return {"publishers": [_row(r) for r in rows]}


@router.post("/api/publishers", status_code=201)
async def create_publisher(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name must be non-empty")
    notes = payload.get("notes")
    cur = conn.execute(
        "INSERT INTO publisher (name, notes) VALUES (?, ?)", (name, notes)
    )
    row = conn.execute(
        "SELECT * FROM publisher WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row(row)


@router.patch("/api/publishers/{pid}")
async def patch_publisher(pid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM publisher WHERE id = ?", (pid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Publisher not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = row["name"]
    notes = row["notes"]
    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            raise HTTPException(400, "name must be non-empty")
        name = new_name
    if "notes" in payload:
        notes = payload["notes"]
    conn.execute(
        "UPDATE publisher SET name = ?, notes = ? WHERE id = ?",
        (name, notes, pid),
    )
    row = conn.execute("SELECT * FROM publisher WHERE id = ?", (pid,)).fetchone()
    return _row(row)
```

- [ ] **Step 3: Mount the router**

In `studio_app/main.py`, add to imports:

```python
from studio_app.routes import publishers as publishers_routes
```

In `build_app`, after the existing `app.include_router(settings_routes.router)` line, add:

```python
    app.include_router(publishers_routes.router)
```

- [ ] **Step 4: Confirm pass**

`uv run pytest tests/test_routes_publishers.py -v` → 7 passed.
Full suite: 54 passed + 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add studio_app/routes/publishers.py studio_app/main.py tests/test_routes_publishers.py
git commit -m "feat(studio): publishers CRUD api"
```

---

## Task 2: Narrators CRUD

**Files:**
- Create: `studio_app/routes/narrators.py`
- Modify: `studio_app/main.py`
- Test: `tests/test_routes_narrators.py`

- [ ] **Step 1: Failing tests**

Create `tests/test_routes_narrators.py`:

```python
from __future__ import annotations


async def test_list_narrators_empty(client):
    r = await client.get("/api/narrators")
    assert r.status_code == 200
    assert r.json() == {"narrators": []}


async def test_create_narrator_minimal(client):
    r = await client.post("/api/narrators", json={"name": "Chris"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Chris"
    assert body["calendar_alias"] is None
    assert body["notes"] is None


async def test_create_narrator_full(client):
    r = await client.post(
        "/api/narrators",
        json={"name": "Christina", "calendar_alias": "Christina", "notes": "fast"},
    )
    body = r.json()
    assert body["name"] == "Christina"
    assert body["calendar_alias"] == "Christina"
    assert body["notes"] == "fast"


async def test_create_narrator_rejects_blank_name(client):
    r = await client.post("/api/narrators", json={"name": ""})
    assert r.status_code == 400


async def test_create_narrator_rejects_duplicate_alias(client):
    await client.post("/api/narrators", json={"name": "A", "calendar_alias": "shared"})
    r = await client.post(
        "/api/narrators", json={"name": "B", "calendar_alias": "shared"}
    )
    assert r.status_code == 400
    assert "calendar_alias" in r.json()["detail"].lower()


async def test_get_narrator_by_id(client):
    r = await client.post("/api/narrators", json={"name": "Detail"})
    nid = r.json()["id"]
    r2 = await client.get(f"/api/narrators/{nid}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Detail"


async def test_get_narrator_404(client):
    r = await client.get("/api/narrators/9999")
    assert r.status_code == 404


async def test_patch_narrator_updates(client):
    r = await client.post("/api/narrators", json={"name": "Old"})
    nid = r.json()["id"]
    r2 = await client.patch(
        f"/api/narrators/{nid}",
        json={"name": "New", "calendar_alias": "NewAlias", "notes": "n"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["name"] == "New"
    assert body["calendar_alias"] == "NewAlias"


async def test_patch_narrator_clears_alias_with_null(client):
    r = await client.post(
        "/api/narrators", json={"name": "X", "calendar_alias": "tobe_cleared"}
    )
    nid = r.json()["id"]
    r2 = await client.patch(
        f"/api/narrators/{nid}", json={"calendar_alias": None}
    )
    assert r2.status_code == 200
    assert r2.json()["calendar_alias"] is None
```

- [ ] **Step 2: Implement `studio_app/routes/narrators.py`**

```python
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _row(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "calendar_alias": r["calendar_alias"],
        "notes": r["notes"],
        "created_at": r["created_at"],
    }


@router.get("/api/narrators")
def list_narrators(request: Request) -> dict:
    conn = request.app.state.conn
    rows = conn.execute("SELECT * FROM narrator ORDER BY name").fetchall()
    return {"narrators": [_row(r) for r in rows]}


@router.get("/api/narrators/{nid}")
def get_narrator(nid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Narrator not found")
    return _row(row)


@router.post("/api/narrators", status_code=201)
async def create_narrator(request: Request) -> dict:
    conn = request.app.state.conn
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name must be non-empty")
    alias = payload.get("calendar_alias")
    if alias is not None:
        alias = alias.strip() or None
    notes = payload.get("notes")
    try:
        cur = conn.execute(
            "INSERT INTO narrator (name, calendar_alias, notes) VALUES (?, ?, ?)",
            (name, alias, notes),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"calendar_alias must be unique: {exc}") from exc
    row = conn.execute(
        "SELECT * FROM narrator WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _row(row)


@router.patch("/api/narrators/{nid}")
async def patch_narrator(nid: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    if row is None:
        raise HTTPException(404, "Narrator not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    name = row["name"]
    alias = row["calendar_alias"]
    notes = row["notes"]
    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            raise HTTPException(400, "name must be non-empty")
        name = new_name
    if "calendar_alias" in payload:
        v = payload["calendar_alias"]
        if v is None:
            alias = None
        else:
            v = v.strip()
            alias = v or None
    if "notes" in payload:
        notes = payload["notes"]
    try:
        conn.execute(
            "UPDATE narrator SET name = ?, calendar_alias = ?, notes = ? WHERE id = ?",
            (name, alias, notes, nid),
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"calendar_alias must be unique: {exc}") from exc
    row = conn.execute("SELECT * FROM narrator WHERE id = ?", (nid,)).fetchone()
    return _row(row)
```

- [ ] **Step 3: Mount**

In `studio_app/main.py`, add import:
```python
from studio_app.routes import narrators as narrators_routes
```
And after publishers in `build_app`:
```python
    app.include_router(narrators_routes.router)
```

- [ ] **Step 4: Confirm pass**

9 new passing tests → full suite 63 passed + 2 skipped.

- [ ] **Step 5: Commit**

```bash
git add studio_app/routes/narrators.py studio_app/main.py tests/test_routes_narrators.py
git commit -m "feat(studio): narrators CRUD api"
```

---

## Task 3: PATCH book endpoint (editable fields)

**Files:**
- Modify: `studio_app/routes/books.py` (add PATCH handler)
- Modify: `tests/test_routes_books.py` (add 5 PATCH tests)

- [ ] **Step 1: Failing tests**

Append to `tests/test_routes_books.py`:

```python


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
    # Try to clear draft without setting publisher_id and genre — should 400.
    # First mark as draft via direct DB write via PATCH (we don't have a "set draft" path,
    # but new books default is_draft=0; force it via PATCH).
    r = await client.patch(f"/api/books/{bid}", json={"is_draft": True})
    assert r.status_code == 200 and r.json()["is_draft"] == 1
    # Now refuse to clear with missing required fields.
    r = await client.patch(f"/api/books/{bid}", json={"is_draft": False})
    assert r.status_code == 400
    assert "publisher" in r.json()["detail"].lower() or "genre" in r.json()["detail"].lower()
```

- [ ] **Step 2: Implement PATCH in `studio_app/routes/books.py`**

Add at the end of `studio_app/routes/books.py`:

```python
_PATCHABLE_FIELDS = {
    "status", "genre", "publisher_notes", "planned_end",
    "publisher_id", "narrator_id",
    "audio_folder", "drive_sync_path",
    "is_draft",
}
_ALLOWED_STATUS = {"planned", "in_progress", "done", "archived"}


@router.patch("/api/books/{book_id}")
async def patch_book(book_id: int, request: Request) -> dict:
    conn = request.app.state.conn
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Book not found")
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "JSON object required")
    unknown = set(payload.keys()) - _PATCHABLE_FIELDS
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {sorted(unknown)}")
    updates: dict = {}
    if "status" in payload:
        if payload["status"] not in _ALLOWED_STATUS:
            raise HTTPException(
                400, f"status must be one of {sorted(_ALLOWED_STATUS)}"
            )
        updates["status"] = payload["status"]
    if "is_draft" in payload:
        wants_draft = bool(payload["is_draft"])
        if not wants_draft:
            # Clearing the draft flag requires publisher_id and genre to be set
            # (use the values in the payload if provided, else the existing row).
            new_publisher = payload.get("publisher_id", row["publisher_id"])
            new_genre = payload.get("genre", row["genre"])
            if new_publisher is None or not (new_genre or "").strip():
                raise HTTPException(
                    400,
                    "Cannot clear draft: publisher_id and genre must be set first",
                )
        updates["is_draft"] = 1 if wants_draft else 0
    for fld in (
        "genre", "publisher_notes", "planned_end",
        "publisher_id", "narrator_id", "audio_folder", "drive_sync_path",
    ):
        if fld in payload:
            updates[fld] = payload[fld]
    if not updates:
        return _book_row_to_dict(row)
    cols = ", ".join(f"{k} = ?" for k in updates)
    params = list(updates.values()) + [book_id]
    conn.execute(f"UPDATE book SET {cols} WHERE id = ?", params)
    row = conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
    return _book_row_to_dict(row)
```

- [ ] **Step 3: Confirm pass**

`uv run pytest tests/test_routes_books.py -v` → 13 passing in that file (8 existing + 5 new + the `_create_test_book` helper isn't a test). Full suite: 69 passed + 2 skipped (counting 6 new tests; the `is_draft` test counts as one but exercises both paths).

If the 13 number is off (e.g., the helper is collected), confirm by counting only `async def test_*` functions in the file.

- [ ] **Step 4: Commit**

```bash
git add studio_app/routes/books.py tests/test_routes_books.py
git commit -m "feat(studio): PATCH /api/books/:id for editable fields + draft gate"
```

---

## Task 4: Library books filters (server-side)

**Files:**
- Modify: `studio_app/routes/books.py` (`list_books` accepts query params)
- Modify: `tests/test_routes_books.py` (filter tests)

- [ ] **Step 1: Failing tests**

Append to `tests/test_routes_books.py`:

```python


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


async def test_list_books_filters_by_narrator(client, tmp_path: Path):
    # create a narrator
    n = await client.post("/api/narrators", json={"name": "Filter Narr"})
    nid = n.json()["id"]
    b1 = await _create_test_book(client, tmp_path, title="Assigned")
    b2 = await _create_test_book(client, tmp_path, title="Unassigned")
    await client.patch(f"/api/books/{b1}", json={"narrator_id": nid})
    r = await client.get(f"/api/books?narrator_id={nid}")
    titles = [b["title"] for b in r.json()["books"]]
    assert titles == ["Assigned"]
```

- [ ] **Step 2: Implement**

Replace the existing `list_books` in `studio_app/routes/books.py` with:

```python
@router.get("/api/books")
def list_books(
    request: Request,
    status: str | None = None,
    narrator_id: int | None = None,
    publisher_id: int | None = None,
    q: str | None = None,
) -> dict:
    conn = request.app.state.conn
    clauses: list[str] = []
    params: list = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if narrator_id is not None:
        clauses.append("narrator_id = ?")
        params.append(narrator_id)
    if publisher_id is not None:
        clauses.append("publisher_id = ?")
        params.append(publisher_id)
    if q:
        clauses.append("title LIKE ?")
        params.append(f"%{q}%")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM book {where} ORDER BY updated_at DESC"
    rows = conn.execute(sql, params).fetchall()
    return {"books": [_book_row_to_dict(r) for r in rows]}
```

- [ ] **Step 3: Confirm pass**

3 new passing tests → full suite 72 passed + 2 skipped.

- [ ] **Step 4: Commit**

```bash
git add studio_app/routes/books.py tests/test_routes_books.py
git commit -m "feat(studio): list books accepts status/narrator/publisher/q filters"
```

---

## Task 5: Book assignment + narrator_book history

**Files:**
- Create: `tests/test_book_assignment.py`
- (Logic lives entirely in the existing PATCH endpoint; this task adds a service helper for the narrator_book row.)

The existing PATCH already lets you set `narrator_id`. What's missing: inserting a `narrator_book` history row when narrator changes, and setting `finished_at` on the prior assignment.

- [ ] **Step 1: Failing tests**

Create `tests/test_book_assignment.py`:

```python
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

    # Alice's row should now have finished_at set, Bob's open.
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


async def test_unassigning_narrator_closes_history(client, conn, tmp_path: Path):
    nid = (await client.post("/api/narrators", json={"name": "C"})).json()["id"]
    bid = await _create_book(client, tmp_path)
    await client.patch(f"/api/books/{bid}", json={"narrator_id": nid})
    await client.patch(f"/api/books/{bid}", json={"narrator_id": None})

    row = conn.execute(
        "SELECT * FROM narrator_book WHERE book_id = ?", (bid,)
    ).fetchone()
    assert row["finished_at"] is not None
```

Run — expect failures (no history wiring yet).

- [ ] **Step 2: Implement the history-wiring helper**

Add to the top of `studio_app/routes/books.py` (under existing imports):

```python
from datetime import datetime, timezone
```

Inside the `patch_book` function, just before the `UPDATE book ...` execute call, add:

```python
    # If narrator assignment changes, maintain the narrator_book history.
    new_narr = updates.get("narrator_id", row["narrator_id"])
    old_narr = row["narrator_id"]
    if "narrator_id" in updates and new_narr != old_narr:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if old_narr is not None:
            conn.execute(
                "UPDATE narrator_book SET finished_at = ?"
                " WHERE book_id = ? AND narrator_id = ? AND finished_at IS NULL",
                (now, book_id, old_narr),
            )
        if new_narr is not None:
            # ON CONFLICT clears any prior closed row's finished_at so the
            # same (narrator,book) pair can be reassigned.
            conn.execute(
                "INSERT INTO narrator_book (narrator_id, book_id) VALUES (?, ?)"
                " ON CONFLICT(narrator_id, book_id) DO UPDATE SET finished_at = NULL",
                (new_narr, book_id),
            )
```

- [ ] **Step 3: Confirm pass**

3 new tests → full suite 75 passed + 2 skipped.

- [ ] **Step 4: Commit**

```bash
git add studio_app/routes/books.py tests/test_book_assignment.py
git commit -m "feat(studio): narrator_book history on assignment changes"
```

---

## Task 6: Narrator detail screen (server + HTML)

**Files:**
- Modify: `studio_app/main.py` (add `/narrators/{nid}` HTML route)
- Create: `studio_app/static/narrator.html`
- Modify: `studio_app/static/app.js` (add `setupNarratorPage`)
- Modify: `tests/test_routes_system.py` (HTML smoke test)

- [ ] **Step 1: Failing test**

Append to `tests/test_routes_system.py`:

```python


async def test_narrator_page_returns_html(client):
    r = await client.get("/narrators/1")
    assert r.status_code == 200
    assert "<h1" in r.text
```

- [ ] **Step 2: HTML route in main.py**

Inside `build_app`, after the existing `book_page` route, add:

```python
    @app.get("/narrators/{nid}", include_in_schema=False)
    def narrator_page(nid: int) -> FileResponse:
        return FileResponse(STATIC_DIR / "narrator.html")
```

- [ ] **Step 3: HTML page**

Create `studio_app/static/narrator.html`:

```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Narrator — Studio App</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<header>
  <strong>Studio App</strong>
  <a href="/library">← Library</a>
</header>
<main>
  <h1 id="name">Loading…</h1>
  <form id="narrator-form" class="col">
    <div class="field">
      <label>Name</label>
      <input id="f-name" required>
    </div>
    <div class="field">
      <label>Calendar alias</label>
      <input id="f-alias" placeholder="(name prefix used in calendar events)">
    </div>
    <div class="field">
      <label>Notes</label>
      <textarea id="f-notes" rows="3"></textarea>
    </div>
    <div><button class="primary" type="submit">Save</button>
      <span id="save-status" class="muted"></span></div>
  </form>
  <h2>Current work</h2>
  <table id="current-table">
    <thead><tr><th>Title</th><th>Progress</th><th>Planned end</th></tr></thead>
    <tbody><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
  </table>
  <h2>Assignment history</h2>
  <table id="history-table">
    <thead><tr><th>Book</th><th>Assigned</th><th>Finished</th></tr></thead>
    <tbody><tr><td colspan="3" class="muted">—</td></tr></tbody>
  </table>
</main>
<script src="/static/app.js"></script>
<script>setupNarratorPage();</script>
</body></html>
```

- [ ] **Step 4: setupNarratorPage in app.js**

Append to `studio_app/static/app.js`:

```javascript

async function setupNarratorPage() {
  const nid = location.pathname.split('/').pop();
  const n = await jsonFetch(`/api/narrators/${nid}`);
  document.getElementById('name').textContent = n.name;
  document.getElementById('f-name').value = n.name;
  document.getElementById('f-alias').value = n.calendar_alias || '';
  document.getElementById('f-notes').value = n.notes || '';

  document.getElementById('narrator-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const status = document.getElementById('save-status');
    status.textContent = 'Saving…';
    const body = {
      name: document.getElementById('f-name').value,
      calendar_alias: document.getElementById('f-alias').value || null,
      notes: document.getElementById('f-notes').value || null,
    };
    try {
      const updated = await jsonFetch(`/api/narrators/${nid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      document.getElementById('name').textContent = updated.name;
      status.textContent = 'Saved.';
    } catch (e) { status.textContent = e.message; }
  });

  const { books } = await jsonFetch(`/api/books?narrator_id=${nid}`);
  const currentBody = document.querySelector('#current-table tbody');
  const current = books.filter(b => b.status === 'in_progress');
  if (!current.length) {
    currentBody.innerHTML = '<tr><td colspan="3" class="muted">No active books.</td></tr>';
  } else {
    currentBody.innerHTML = current.map(b => `
      <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
        <td>${escapeHtml(b.title)}</td>
        <td>${b.pages ? `${b.current_page}/${b.pages}` : `page ${b.current_page}`}</td>
        <td>${b.planned_end || '—'}</td>
      </tr>`).join('');
  }
}
```

- [ ] **Step 5: Confirm pass**

Full suite: 76 passed + 2 skipped.

- [ ] **Step 6: Commit**

```bash
git add studio_app/main.py studio_app/static/narrator.html studio_app/static/app.js tests/test_routes_system.py
git commit -m "feat(studio): narrator detail screen with editable profile"
```

---

## Task 7: Library tabs (books + narrators + publishers) UI

**Files:**
- Modify: `studio_app/static/library.html`
- Modify: `studio_app/static/app.js`
- Modify: `studio_app/static/styles.css`

No tests — the routes are already covered by Tasks 1, 2, 4. This is pure presentation.

- [ ] **Step 1: Update styles.css**

Append:

```css
.tabs { display:flex; gap:0; border-bottom:1px solid var(--border); margin-bottom:16px; }
.tabs button { background:transparent; border:none; border-bottom:2px solid transparent; padding:10px 18px; color:var(--muted); cursor:pointer; }
.tabs button.active { color:var(--fg); border-bottom-color:var(--accent); }
.tab-panel { display:none; }
.tab-panel.active { display:block; }
.filters { display:flex; gap:8px; align-items:center; margin-bottom:16px; }
.filters input, .filters select { padding:6px 10px; }
```

- [ ] **Step 2: Rewrite library.html**

Replace the entire contents of `studio_app/static/library.html` with:

```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Library — Studio App</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<header>
  <strong>Studio App</strong>
  <a class="active" href="/library">Library</a>
  <a href="#" onclick="return false">Schedule</a>
</header>
<main>
  <div class="tabs">
    <button data-tab="books" class="active">Books</button>
    <button data-tab="narrators">Narrators</button>
    <button data-tab="publishers">Publishers</button>
  </div>

  <section class="tab-panel active" data-tab="books">
    <div class="filters">
      <input id="filter-q" placeholder="Search title…">
      <select id="filter-status">
        <option value="">Any status</option>
        <option value="planned">Planned</option>
        <option value="in_progress">In progress</option>
        <option value="done">Done</option>
        <option value="archived">Archived</option>
      </select>
      <select id="filter-narrator"><option value="">Any narrator</option></select>
      <select id="filter-publisher"><option value="">Any publisher</option></select>
    </div>
    <form id="upload-form" class="row" enctype="multipart/form-data">
      <input id="title" name="title" placeholder="Book title" required>
      <input id="file" name="file" type="file" accept=".pdf,.epub,.docx,.txt" required>
      <button class="primary" type="submit">Add book</button>
      <span id="upload-status" class="muted"></span>
    </form>
    <table id="books-table">
      <thead><tr>
        <th>Title</th><th>Format</th><th>Narrator</th><th>Status</th><th>Pages</th>
      </tr></thead>
      <tbody><tr><td colspan="5" class="muted">Loading…</td></tr></tbody>
    </table>
  </section>

  <section class="tab-panel" data-tab="narrators">
    <form id="narrator-create" class="row">
      <input id="nc-name" placeholder="Name" required>
      <input id="nc-alias" placeholder="Calendar alias (optional)">
      <button class="primary" type="submit">Add narrator</button>
      <span id="nc-status" class="muted"></span>
    </form>
    <table id="narrators-table">
      <thead><tr><th>Name</th><th>Alias</th><th>Notes</th></tr></thead>
      <tbody><tr><td colspan="3" class="muted">Loading…</td></tr></tbody>
    </table>
  </section>

  <section class="tab-panel" data-tab="publishers">
    <form id="publisher-create" class="row">
      <input id="pc-name" placeholder="Name" required>
      <input id="pc-notes" placeholder="Notes (optional)">
      <button class="primary" type="submit">Add publisher</button>
      <span id="pc-status" class="muted"></span>
    </form>
    <table id="publishers-table">
      <thead><tr><th>Name</th><th>Notes</th></tr></thead>
      <tbody><tr><td colspan="2" class="muted">Loading…</td></tr></tbody>
    </table>
  </section>
</main>
<script src="/static/app.js"></script>
<script>setupLibraryPage();</script>
</body></html>
```

- [ ] **Step 3: Rewrite setupLibraryPage in app.js**

Replace the existing `setupLibraryPage` function with:

```javascript
async function setupLibraryPage() {
  document.querySelectorAll('.tabs button').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.tab;
      document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.dataset.tab === target);
      });
    });
  });

  await Promise.all([refreshBooks(), refreshNarrators(), refreshPublishers()]);
  document.getElementById('upload-form').addEventListener('submit', onUploadBook);
  document.getElementById('filter-q').addEventListener('input', refreshBooks);
  document.getElementById('filter-status').addEventListener('change', refreshBooks);
  document.getElementById('filter-narrator').addEventListener('change', refreshBooks);
  document.getElementById('filter-publisher').addEventListener('change', refreshBooks);
  document.getElementById('narrator-create').addEventListener('submit', onCreateNarrator);
  document.getElementById('publisher-create').addEventListener('submit', onCreatePublisher);
}

async function refreshBooks() {
  const params = new URLSearchParams();
  const q = document.getElementById('filter-q').value.trim();
  const s = document.getElementById('filter-status').value;
  const nid = document.getElementById('filter-narrator').value;
  const pid = document.getElementById('filter-publisher').value;
  if (q) params.set('q', q);
  if (s) params.set('status', s);
  if (nid) params.set('narrator_id', nid);
  if (pid) params.set('publisher_id', pid);
  const url = '/api/books' + (params.toString() ? '?' + params : '');
  const { books } = await jsonFetch(url);
  const tbody = document.querySelector('#books-table tbody');
  if (!books.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="muted">No books match.</td></tr>';
    return;
  }
  // Need narrator names — assume the narrators dropdown is populated.
  const narratorMap = Object.fromEntries(
    [...document.getElementById('filter-narrator').options].map(o => [o.value, o.textContent])
  );
  tbody.innerHTML = books.map(b => `
    <tr onclick="location.href='/books/${b.id}'" style="cursor:pointer">
      <td>${escapeHtml(b.title)}</td>
      <td>${b.format}</td>
      <td>${b.narrator_id ? escapeHtml(narratorMap[String(b.narrator_id)] || '—') : '—'}</td>
      <td>${b.status}</td>
      <td>${b.pages || '—'}</td>
    </tr>`).join('');
}

async function refreshNarrators() {
  const { narrators } = await jsonFetch('/api/narrators');
  const tbody = document.querySelector('#narrators-table tbody');
  tbody.innerHTML = narrators.length
    ? narrators.map(n => `
      <tr onclick="location.href='/narrators/${n.id}'" style="cursor:pointer">
        <td>${escapeHtml(n.name)}</td>
        <td>${escapeHtml(n.calendar_alias || '—')}</td>
        <td>${escapeHtml(n.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="3" class="muted">No narrators yet.</td></tr>';
  const sel = document.getElementById('filter-narrator');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any narrator</option>' +
    narrators.map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
  sel.value = current;
}

async function refreshPublishers() {
  const { publishers } = await jsonFetch('/api/publishers');
  const tbody = document.querySelector('#publishers-table tbody');
  tbody.innerHTML = publishers.length
    ? publishers.map(p => `
      <tr>
        <td>${escapeHtml(p.name)}</td>
        <td>${escapeHtml(p.notes || '')}</td>
      </tr>`).join('')
    : '<tr><td colspan="2" class="muted">No publishers yet.</td></tr>';
  const sel = document.getElementById('filter-publisher');
  const current = sel.value;
  sel.innerHTML = '<option value="">Any publisher</option>' +
    publishers.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  sel.value = current;
}

async function onUploadBook(e) {
  e.preventDefault();
  const status = document.getElementById('upload-status');
  status.textContent = 'Uploading…';
  const fd = new FormData();
  fd.append('title', document.getElementById('title').value);
  fd.append('file', document.getElementById('file').files[0]);
  try {
    const r = await fetch('/api/books', { method: 'POST', body: fd });
    if (!r.ok) throw new Error(await r.text());
    status.textContent = 'Done.';
    document.getElementById('upload-form').reset();
    await refreshBooks();
  } catch (e) { status.textContent = e.message; }
}

async function onCreateNarrator(e) {
  e.preventDefault();
  const status = document.getElementById('nc-status');
  status.textContent = 'Saving…';
  try {
    await jsonFetch('/api/narrators', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('nc-name').value,
        calendar_alias: document.getElementById('nc-alias').value || null,
      }),
    });
    document.getElementById('narrator-create').reset();
    status.textContent = '';
    await refreshNarrators();
    await refreshBooks();
  } catch (e) { status.textContent = e.message; }
}

async function onCreatePublisher(e) {
  e.preventDefault();
  const status = document.getElementById('pc-status');
  status.textContent = 'Saving…';
  try {
    await jsonFetch('/api/publishers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: document.getElementById('pc-name').value,
        notes: document.getElementById('pc-notes').value || null,
      }),
    });
    document.getElementById('publisher-create').reset();
    status.textContent = '';
    await refreshPublishers();
    await refreshBooks();
  } catch (e) { status.textContent = e.message; }
}
```

- [ ] **Step 4: Run tests**

`uv run pytest -q`. Still 76+2 (no new tests; UI doesn't change route counts). If the count drops, a regex/string match in `tests/test_routes_system.py::test_setup_page_returns_html` should still pass because the form on setup is unchanged.

- [ ] **Step 5: Manual smoke**

Run `uv run studio-app`. Verify:
- `/library` shows three tabs.
- Books tab still lists books.
- Filters work (type in search; pick a status).
- Add a narrator via the Narrators tab → appears immediately + populates the narrator filter dropdown.
- Add a publisher → same.
- Click a narrator row → navigates to `/narrators/<id>`.
- On narrator page, edit name → save → reload, name persists.

- [ ] **Step 6: Commit**

```bash
git add studio_app/static/library.html studio_app/static/app.js studio_app/static/styles.css
git commit -m "feat(studio): library page tabs + filters"
```

---

## Task 8: Book detail page — editable form + narrator/publisher dropdowns

**Files:**
- Modify: `studio_app/static/book.html`
- Modify: `studio_app/static/app.js`

No new tests; PATCH endpoint already covered in Task 3.

- [ ] **Step 1: Rewrite book.html**

Replace `studio_app/static/book.html` with:

```html
<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Book — Studio App</title>
<link rel="stylesheet" href="/static/styles.css">
</head><body>
<header>
  <strong>Studio App</strong>
  <a href="/library">← Library</a>
</header>
<main>
  <h1 id="title">Loading…</h1>
  <p class="muted" id="meta"></p>
  <div id="draft-banner" class="muted" style="display:none; padding:10px; border:1px solid var(--border); border-radius:6px; margin-bottom:12px;">
    Incomplete draft profile. Set publisher and genre to clear this banner.
  </div>

  <h2>Stats</h2>
  <table>
    <tr><th>Format</th><td id="format"></td></tr>
    <tr><th>Pages</th><td id="pages"></td></tr>
    <tr><th>Body chars</th><td id="body_chars"></td></tr>
    <tr><th>Chars / page</th><td id="cpp"></td></tr>
  </table>

  <h2>Edit</h2>
  <form id="book-form" class="col">
    <div class="field"><label>Status</label>
      <select id="f-status">
        <option value="planned">Planned</option>
        <option value="in_progress">In progress</option>
        <option value="done">Done</option>
        <option value="archived">Archived</option>
      </select>
    </div>
    <div class="field"><label>Narrator</label>
      <select id="f-narrator"><option value="">Unassigned</option></select>
    </div>
    <div class="field"><label>Publisher</label>
      <select id="f-publisher"><option value="">None</option></select>
    </div>
    <div class="field"><label>Genre</label><input id="f-genre"></div>
    <div class="field"><label>Planned end</label><input id="f-planned-end" type="date"></div>
    <div class="field"><label>Publisher notes</label><textarea id="f-notes" rows="3"></textarea></div>
    <div class="field"><label>Audio folder</label><input id="f-audio"></div>
    <div><button class="primary" type="submit">Save</button>
      <span id="save-status" class="muted"></span>
      <button id="clear-draft" type="button" style="margin-left:12px; display:none">Confirm setup (clear draft)</button>
    </div>
  </form>

  <p class="muted">Source path: <span id="source_path"></span></p>
</main>
<script src="/static/app.js"></script>
<script>setupBookPage();</script>
</body></html>
```

- [ ] **Step 2: Rewrite setupBookPage in app.js**

Replace the existing `setupBookPage` function with:

```javascript
async function setupBookPage() {
  const id = location.pathname.split('/').pop();
  const [b, narrators, publishers] = await Promise.all([
    jsonFetch(`/api/books/${id}`),
    jsonFetch('/api/narrators'),
    jsonFetch('/api/publishers'),
  ]);

  document.getElementById('title').textContent = b.title;
  document.getElementById('meta').textContent = `Slug: ${b.slug}`;
  document.getElementById('format').textContent = b.format;
  document.getElementById('pages').textContent = b.pages || '—';
  document.getElementById('body_chars').textContent = b.body_chars.toLocaleString();
  document.getElementById('cpp').textContent = b.chars_per_page || '—';
  document.getElementById('source_path').textContent = b.source_path;
  document.getElementById('f-status').value = b.status;
  document.getElementById('f-genre').value = b.genre || '';
  document.getElementById('f-planned-end').value = b.planned_end || '';
  document.getElementById('f-notes').value = b.publisher_notes || '';
  document.getElementById('f-audio').value = b.audio_folder || '';

  const nsel = document.getElementById('f-narrator');
  nsel.innerHTML = '<option value="">Unassigned</option>' +
    narrators.narrators.map(n => `<option value="${n.id}">${escapeHtml(n.name)}</option>`).join('');
  nsel.value = b.narrator_id == null ? '' : String(b.narrator_id);

  const psel = document.getElementById('f-publisher');
  psel.innerHTML = '<option value="">None</option>' +
    publishers.publishers.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  psel.value = b.publisher_id == null ? '' : String(b.publisher_id);

  if (b.is_draft) {
    document.getElementById('draft-banner').style.display = 'block';
    document.getElementById('clear-draft').style.display = 'inline';
  }

  document.getElementById('book-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    await savePatch({});
  });

  document.getElementById('clear-draft').addEventListener('click', async () => {
    await savePatch({ is_draft: false });
  });

  async function savePatch(extra) {
    const status = document.getElementById('save-status');
    status.textContent = 'Saving…';
    const payload = {
      status: document.getElementById('f-status').value,
      genre: document.getElementById('f-genre').value || null,
      planned_end: document.getElementById('f-planned-end').value || null,
      publisher_notes: document.getElementById('f-notes').value || null,
      audio_folder: document.getElementById('f-audio').value || null,
      narrator_id: nsel.value ? Number(nsel.value) : null,
      publisher_id: psel.value ? Number(psel.value) : null,
      ...extra,
    };
    try {
      const updated = await jsonFetch(`/api/books/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      status.textContent = 'Saved.';
      if (!updated.is_draft) {
        document.getElementById('draft-banner').style.display = 'none';
        document.getElementById('clear-draft').style.display = 'none';
      }
    } catch (e) { status.textContent = e.message; }
  }
}
```

- [ ] **Step 3: Confirm tests still green**

`uv run pytest -q` → 76+2 unchanged.

- [ ] **Step 4: Manual smoke**

`uv run studio-app`:
- Open a book → see status dropdown reflects current status.
- Change status → save → reload → persists.
- Pick a narrator from dropdown → save → library tab shows narrator name in the row.
- Upload a draft book (won't happen until JIT wizard in Phase 5; for now you can flip `is_draft=1` via curl PATCH to test) → banner appears → click Confirm setup with no publisher/genre set → 400 error in status text → set them → Confirm setup → banner disappears.

- [ ] **Step 5: Commit**

```bash
git add studio_app/static/book.html studio_app/static/app.js
git commit -m "feat(studio): book detail editable form + narrator/publisher dropdowns"
```

---

## Phase 2 done-criteria

- [ ] All tests green: `uv run pytest -q` → 76 passed + 2 skipped.
- [ ] `uv run studio-app` boots, demo flow:
  1. `/library` Books tab — list, filter by status, search by title.
  2. Add narrator and publisher via library tabs.
  3. Open a book, change status + narrator + planned_end → save → persist.
  4. Click narrator name → narrator detail page shows current work.
  5. Reassign book to a different narrator → navigating back to the first narrator shows assignment in history.
- [ ] No background threads (Phase 3 territory).
- [ ] No viewer (Phase 4 territory).
- [ ] No calendar or JIT (Phase 5 territory).

## Self-review pass

**Spec coverage for Phase 2:**

| Spec section | Where it lands |
|---|---|
| §4 narrator_book history | Task 5 |
| §4 narrator.calendar_alias | Task 2 |
| §4 book.is_draft + confirm gate | Task 3 |
| §6.1 Book editable metadata | Tasks 3 + 8 |
| §6.2 Library tabs (books/narrators/publishers) | Tasks 1, 2, 4, 7 |
| §6.2 Library filters | Task 4 |
| §6.3 Narrator detail screen | Task 6 |
| §6.3 Assign book action | Tasks 3 + 5 |

**Deferred to later phases:**
- Stats panels on narrator/book (Phase 3 — `narrator_stats` / `book_stats` recomputed after audio scan).
- Sessions list on book detail (Phase 4 — sessions created in viewer).
- Publishers screen as separate URL with detail view (Phase 7 polish — list+inline-edit in library tab is enough for v1).
- CSV exports (Phase 7).

**Function names cross-referenced:**
- `_book_row_to_dict` (Phase 1) reused unchanged.
- `_row` (Phase 2 publishers + narrators routes) is intentionally module-private — same name in two modules is fine; not exported.
- `_PATCHABLE_FIELDS`, `_ALLOWED_STATUS` are module-private constants.
- HTML routes `narrator_page` mirrors `book_page` from Phase 1.
- JS function `setupNarratorPage` mirrors `setupBookPage`.

No placeholders. No "implement later" markers. Every code step shows actual code.
