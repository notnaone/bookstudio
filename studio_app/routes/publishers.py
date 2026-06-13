from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from studio_app.db_lock import hold

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
    with hold(request.app.state.db_lock):
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
    with hold(request.app.state.db_lock):
        conn.execute(
            "UPDATE publisher SET name = ?, notes = ? WHERE id = ?",
            (name, notes, pid),
        )
        row = conn.execute("SELECT * FROM publisher WHERE id = ?", (pid,)).fetchone()
    return _row(row)
