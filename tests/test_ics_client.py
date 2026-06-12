from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from studio_app.ics_client import CalendarEvent, fetch_ics, parse_ics

FIXTURE = Path(__file__).parent / "fixtures" / "sample.ics"


def test_parse_ics_fixture_returns_three_events() -> None:
    events = parse_ics(FIXTURE.read_bytes())
    assert len(events) == 3
    assert {e.uid for e in events} == {
        "evt-chris-foo@bookstudio.test",
        "evt-christina-bar@bookstudio.test",
        "evt-studio-booking@bookstudio.test",
    }


def test_parse_ics_normalizes_times_to_utc() -> None:
    events = parse_ics(FIXTURE.read_bytes())
    chris = next(e for e in events if "Chris - Foo" in e.summary)
    assert chris.summary == "Chris - Foo"
    assert chris.description == "Recording session for Chris"
    assert chris.dtstart == datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)
    assert chris.dtend == datetime(2026, 6, 15, 11, 0, tzinfo=timezone.utc)
    assert chris.dtstart.tzinfo is timezone.utc
    assert chris.dtend.tzinfo is timezone.utc


def test_parse_ics_christina_title_for_alias_trap() -> None:
    events = parse_ics(FIXTURE.read_bytes())
    christina = next(e for e in events if e.summary.startswith("Christina"))
    assert christina.summary == "Christina - Bar"


def test_fetch_ics_raises_on_non_2xx(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status_code = 404
        content = b""

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError(
                "not found",
                request=httpx.Request("GET", "http://example.test/feed.ics"),
                response=httpx.Response(404),
            )

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())
    with pytest.raises(httpx.HTTPStatusError):
        fetch_ics("http://example.test/feed.ics")


def test_fetch_ics_returns_body(monkeypatch: pytest.MonkeyPatch) -> None:
    body = FIXTURE.read_bytes()

    class FakeResponse:
        status_code = 200
        content = body

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: FakeResponse())
    assert fetch_ics("http://example.test/feed.ics") == body
    events = parse_ics(fetch_ics("http://example.test/feed.ics"))
    assert isinstance(events[0], CalendarEvent)
