"""Date-range helpers for schedule list views."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

VALID_RANGES = frozenset({"today", "week", "month", "upcoming", "all"})


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def range_bounds(range_name: str) -> tuple[str | None, str | None]:
    """Return inclusive-from, exclusive-to ISO timestamps in local time."""
    if range_name == "all":
        return None, None

    now = _local_now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if range_name == "today":
        return _iso(start_of_today), _iso(start_of_today + timedelta(days=1))

    if range_name == "week":
        # Monday-based week; show from today through end of Sunday.
        weekday = start_of_today.weekday()  # Mon=0
        end_of_week = start_of_today + timedelta(days=7 - weekday)
        return _iso(start_of_today), _iso(end_of_week)

    if range_name == "month":
        if start_of_today.month == 12:
            end_of_month = start_of_today.replace(
                year=start_of_today.year + 1, month=1, day=1,
            )
        else:
            end_of_month = start_of_today.replace(month=start_of_today.month + 1, day=1)
        return _iso(start_of_today), _iso(end_of_month)

    if range_name == "upcoming":
        return _iso(start_of_today), _iso(start_of_today + timedelta(days=60))

    raise ValueError(f"Unknown range: {range_name}")


def prune_cutoff(*, keep_days_past: int = 7) -> datetime:
    """Drop calendar rows ending before this moment (local midnight - keep_days)."""
    start_of_today = _local_now().replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return start_of_today - timedelta(days=keep_days_past)


def event_is_too_old(event_end: datetime, *, keep_days_past: int = 7) -> bool:
    end = event_end
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return end < prune_cutoff(keep_days_past=keep_days_past).astimezone(end.tzinfo)
