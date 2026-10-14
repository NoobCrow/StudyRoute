"""Escrow release schedules: split an amount into dated tranches. Pure, integer money only.

A tuition payment is one tranche on the due date. Living costs are several equal tranches, one
a month. Every minor unit is kept: when the total does not divide evenly the first tranches get
one extra unit, so the parts always add up to the total.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.engine.money import EngineError

MAX_TRANCHES = 24
CADENCES = ("ONCE", "MONTHLY")


class ScheduleError(EngineError):
    pass


@dataclass(frozen=True)
class ScheduledTranche:
    index: int
    amount_minor: int
    release_on: date


def add_months(start: date, months: int) -> date:
    """The same day `months` later, or the last day of that month if it is shorter."""
    month_index = start.month - 1 + months
    year, month = start.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def split_evenly(total_minor: int, count: int) -> list[int]:
    base, extra = divmod(total_minor, count)
    return [base + 1 if i < extra else base for i in range(count)]


def build_schedule(
    total_minor: int, count: int, first_release: date, cadence: str
) -> tuple[ScheduledTranche, ...]:
    if isinstance(total_minor, bool) or not isinstance(total_minor, int):
        raise ScheduleError("The amount must be a whole number of minor units.")
    if total_minor <= 0:
        raise ScheduleError("The amount must be greater than zero.")
    if not 1 <= count <= MAX_TRANCHES:
        raise ScheduleError(f"Use between 1 and {MAX_TRANCHES} tranches.")
    if cadence not in CADENCES:
        raise ScheduleError("Cadence must be ONCE or MONTHLY.")
    if total_minor < count:
        raise ScheduleError("The amount is too small to split into that many tranches.")
    amounts = split_evenly(total_minor, count)
    return tuple(
        ScheduledTranche(i, amount, add_months(first_release, i) if count > 1 else first_release)
        for i, amount in enumerate(amounts)
    )


def release_timestamp(day: date) -> int:
    """Midnight UTC at the start of `day`, in epoch seconds (what the contract compares)."""
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
