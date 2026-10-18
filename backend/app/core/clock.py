"""Time source. Everything that needs "now" takes a Clock so tests can control time."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Manually advanced clock used by the test-suite and the demo scripts."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware start time")
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def set(self, value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("FakeClock needs a timezone-aware time")
        self._now = value.astimezone(UTC)


def iso_utc(value: datetime) -> str:
    """Format a datetime as ISO 8601 UTC with a Z suffix and second precision."""
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
