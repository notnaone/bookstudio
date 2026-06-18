"""Derive usable event titles from ICS summary/description fields."""

from __future__ import annotations

_GENERIC_SUMMARIES = frozenset({
    "busy",
    "reserved",
    "private",
    "tentative",
    "unavailable",
})


def effective_event_title(summary: str, description: str | None) -> str:
    """Prefer a real title when Google Calendar masks SUMMARY as 'Busy'."""
    title = (summary or "").strip()
    if title.lower() not in _GENERIC_SUMMARIES and title:
        return title
    if description:
        for line in description.replace("\r\n", "\n").split("\n"):
            candidate = line.strip()
            if candidate and candidate.lower() not in _GENERIC_SUMMARIES:
                return candidate
    return title or "Untitled"


def is_generic_title(title: str) -> bool:
    return (title or "").strip().lower() in _GENERIC_SUMMARIES
