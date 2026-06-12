from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from icalendar import Calendar


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    description: str | None
    dtstart: datetime
    dtend: datetime


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_ics(ics_bytes: bytes) -> list[CalendarEvent]:
    """Parse ICS bytes into calendar events using icalendar."""
    cal = Calendar.from_ical(ics_bytes)
    events: list[CalendarEvent] = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("uid", "")).strip()
        if not uid:
            continue
        summary = str(component.get("summary", "")).strip()
        description_raw = component.get("description")
        description = str(description_raw).strip() if description_raw else None
        dtstart = component.decoded("dtstart")
        dtend = component.decoded("dtend")
        if not isinstance(dtstart, datetime) or not isinstance(dtend, datetime):
            continue
        events.append(
            CalendarEvent(
                uid=uid,
                summary=summary,
                description=description,
                dtstart=_to_utc(dtstart),
                dtend=_to_utc(dtend),
            )
        )
    return events


def fetch_ics(url: str, *, timeout: float = 30.0) -> bytes:
    """GET an ICS URL and return the response body."""
    response = httpx.get(url, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return response.content
