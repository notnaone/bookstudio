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
