from __future__ import annotations

import csv
import sqlite3
from io import StringIO
from typing import Iterator


def _csv_line(row: list) -> str:
    buf = StringIO()
    csv.writer(buf).writerow([_csv_safe(v) for v in row])
    return buf.getvalue()


def _csv_safe(value: object) -> object:
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        return value
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _date_clause(
    column: str, from_date: str | None, to_date: str | None
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if from_date:
        clauses.append(f"{column} >= ?")
        params.append(from_date)
    if to_date:
        clauses.append(f"{column} <= ?")
        params.append(to_date)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def export_books_csv(
    conn: sqlite3.Connection,
    *,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Iterator[str]:
    """Yield CSV lines for books export. Column order is stable."""
    header = [
        "id",
        "slug",
        "title",
        "publisher_name",
        "narrator_name",
        "status",
        "pages",
        "body_chars",
        "hours_recorded",
        "progress_pct",
        "planned_end",
        "created_at",
    ]
    yield _csv_line(header)

    sql = (
        "SELECT b.id, b.slug, b.title, p.name AS publisher_name,"
        " n.name AS narrator_name, b.status, b.pages, b.body_chars,"
        " COALESCE(bs.total_audio_seconds, 0) AS total_audio_seconds,"
        " COALESCE(bs.progress_pct, 0) AS progress_pct,"
        " b.planned_end, b.created_at"
        " FROM book b"
        " LEFT JOIN publisher p ON p.id = b.publisher_id"
        " LEFT JOIN narrator n ON n.id = b.narrator_id"
        " LEFT JOIN book_stats bs ON bs.book_id = b.id"
        " WHERE 1=1"
    )
    params: list = []
    if status:
        sql += " AND b.status = ?"
        params.append(status)
    date_sql, date_params = _date_clause("b.created_at", from_date, to_date)
    sql += date_sql
    params.extend(date_params)
    sql += " ORDER BY b.id"

    for row in conn.execute(sql, params).fetchall():
        hours = round(float(row["total_audio_seconds"]) / 3600, 4)
        yield _csv_line([
            row["id"],
            row["slug"],
            row["title"],
            row["publisher_name"] or "",
            row["narrator_name"] or "",
            row["status"],
            row["pages"] or 0,
            row["body_chars"] or 0,
            hours,
            row["progress_pct"],
            row["planned_end"] or "",
            row["created_at"] or "",
        ])


def export_sessions_csv(
    conn: sqlite3.Connection,
    *,
    kind: str = "all",
    from_date: str | None = None,
    to_date: str | None = None,
) -> Iterator[str]:
    """Yield CSV lines for reading + work sessions."""
    header = [
        "id",
        "kind",
        "book_id",
        "book_title",
        "narrator_id",
        "narrator_name",
        "started_at",
        "ended_at",
        "start_page",
        "end_page",
        "active_seconds",
        "auto_closed",
    ]
    yield _csv_line(header)

    rows: list[sqlite3.Row] = []

    if kind in ("all", "reading"):
        sql = (
            "SELECT rs.id, 'reading' AS kind, rs.book_id, b.title AS book_title,"
            " rs.narrator_id, n.name AS narrator_name, rs.started_at, rs.ended_at,"
            " rs.start_page, rs.end_page, rs.active_seconds, rs.auto_closed"
            " FROM reading_session rs"
            " JOIN book b ON b.id = rs.book_id"
            " LEFT JOIN narrator n ON n.id = rs.narrator_id"
            " WHERE 1=1"
        )
        params: list = []
        date_sql, date_params = _date_clause("rs.started_at", from_date, to_date)
        sql += date_sql
        params.extend(date_params)
        sql += " ORDER BY rs.started_at, rs.id"
        rows.extend(conn.execute(sql, params).fetchall())

    if kind in ("all", "recording", "editing"):
        sql = (
            "SELECT ws.id, ws.kind, ws.book_id, b.title AS book_title,"
            " ws.narrator_id, n.name AS narrator_name, ws.started_at, ws.ended_at,"
            " ws.start_page, ws.end_page, NULL AS active_seconds, NULL AS auto_closed"
            " FROM work_session ws"
            " JOIN book b ON b.id = ws.book_id"
            " LEFT JOIN narrator n ON n.id = ws.narrator_id"
            " WHERE 1=1"
        )
        params = []
        if kind in ("recording", "editing"):
            sql += " AND ws.kind = ?"
            params.append(kind)
        date_sql, date_params = _date_clause("ws.started_at", from_date, to_date)
        sql += date_sql
        params.extend(date_params)
        sql += " ORDER BY ws.started_at, ws.id"
        rows.extend(conn.execute(sql, params).fetchall())

    rows.sort(key=lambda r: (r["started_at"] or "", r["kind"], r["id"]))

    for row in rows:
        yield _csv_line([
            row["id"],
            row["kind"],
            row["book_id"],
            row["book_title"],
            row["narrator_id"] or "",
            row["narrator_name"] or "",
            row["started_at"] or "",
            row["ended_at"] or "",
            row["start_page"] if row["start_page"] is not None else "",
            row["end_page"] if row["end_page"] is not None else "",
            row["active_seconds"] if row["active_seconds"] is not None else "",
            row["auto_closed"] if row["auto_closed"] is not None else "",
        ])


def export_audio_files_csv(
    conn: sqlite3.Connection,
    *,
    book_id: int | None = None,
) -> Iterator[str]:
    header = [
        "id",
        "book_id",
        "book_title",
        "filename",
        "duration_seconds",
        "size_bytes",
        "mtime",
        "scanned_at",
    ]
    yield _csv_line(header)

    sql = (
        "SELECT af.id, af.book_id, b.title AS book_title, af.filename,"
        " af.duration_seconds, af.size_bytes, af.mtime, af.scanned_at"
        " FROM audio_file af"
        " JOIN book b ON b.id = af.book_id"
        " WHERE 1=1"
    )
    params: list = []
    if book_id is not None:
        sql += " AND af.book_id = ?"
        params.append(book_id)
    sql += " ORDER BY af.book_id, af.filename"

    for row in conn.execute(sql, params).fetchall():
        yield _csv_line([
            row["id"],
            row["book_id"],
            row["book_title"],
            row["filename"],
            row["duration_seconds"],
            row["size_bytes"],
            row["mtime"] or "",
            row["scanned_at"] or "",
        ])
