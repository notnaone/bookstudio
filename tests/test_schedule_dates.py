from datetime import datetime, timedelta, timezone

from studio_app.schedule_dates import range_bounds


def test_range_bounds_today():
    start, end = range_bounds("today")
    assert start is not None and end is not None
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    assert e - s == timedelta(days=1)


def test_range_bounds_upcoming_is_sixty_days():
    start, end = range_bounds("upcoming")
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    assert e - s == timedelta(days=60)


def test_range_bounds_all():
    assert range_bounds("all") == (None, None)
