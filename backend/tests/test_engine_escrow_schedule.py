"""Escrow release schedules: integer money, no rounding drift, month-end dates."""

from __future__ import annotations

import random
from datetime import date

import pytest

from app.engine.escrow_schedule import (
    MAX_TRANCHES,
    ScheduleError,
    add_months,
    build_schedule,
    release_timestamp,
    split_evenly,
)


def test_an_even_split_keeps_every_minor_unit() -> None:
    assert split_evenly(1_000_000, 4) == [250_000] * 4
    assert split_evenly(100, 3) == [34, 33, 33]
    assert split_evenly(7, 7) == [1] * 7
    assert split_evenly(5, 1) == [5]


def test_the_split_always_adds_up_and_differs_by_at_most_one() -> None:
    rng = random.Random(7)
    for _ in range(500):
        count = rng.randint(1, MAX_TRANCHES)
        total = rng.randint(count, 50_000_000)
        parts = split_evenly(total, count)
        assert sum(parts) == total and len(parts) == count
        assert max(parts) - min(parts) <= 1 and all(p >= 1 for p in parts)
        assert parts == sorted(parts, reverse=True), "the extra units go to the first tranches"


def test_adding_months_keeps_the_day_and_clamps_to_the_month_end() -> None:
    assert add_months(date(2026, 10, 15), 1) == date(2026, 11, 15)
    assert add_months(date(2026, 10, 15), 3) == date(2027, 1, 15)
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)
    assert add_months(date(2026, 1, 31), 2) == date(2026, 3, 31), "the clamp does not stick"
    assert add_months(date(2026, 12, 31), 12) == date(2027, 12, 31)


def test_a_single_tranche_is_one_release_on_the_due_date() -> None:
    schedule = build_schedule(1_000_000, 1, date(2026, 10, 28), "ONCE")
    assert [(t.index, t.amount_minor, t.release_on) for t in schedule] == [
        (0, 1_000_000, date(2026, 10, 28))
    ]


def test_a_monthly_schedule_dates_each_tranche_a_month_apart() -> None:
    schedule = build_schedule(120_000, 4, date(2026, 11, 1), "MONTHLY")
    assert [t.release_on for t in schedule] == [
        date(2026, 11, 1),
        date(2026, 12, 1),
        date(2027, 1, 1),
        date(2027, 2, 1),
    ]
    assert [t.amount_minor for t in schedule] == [30_000] * 4
    assert [t.index for t in schedule] == [0, 1, 2, 3]


def test_a_remainder_goes_to_the_first_tranches() -> None:
    schedule = build_schedule(100_001, 3, date(2026, 11, 30), "MONTHLY")
    assert [t.amount_minor for t in schedule] == [33_334, 33_334, 33_333]
    assert [t.release_on for t in schedule] == [
        date(2026, 11, 30),
        date(2026, 12, 30),
        date(2027, 1, 30),
    ]


@pytest.mark.parametrize(
    ("total", "count"),
    [(0, 1), (-5, 1), (100, 0), (100, MAX_TRANCHES + 1), (3, 4)],
)
def test_impossible_schedules_are_refused(total: int, count: int) -> None:
    with pytest.raises(ScheduleError):
        build_schedule(total, count, date(2026, 11, 1), "MONTHLY")


def test_money_must_be_integer_minor_units() -> None:
    with pytest.raises(ScheduleError):
        build_schedule(100.5, 2, date(2026, 11, 1), "MONTHLY")  # type: ignore[arg-type]
    with pytest.raises(ScheduleError):
        build_schedule(True, 1, date(2026, 11, 1), "ONCE")  # type: ignore[arg-type]


def test_unknown_cadence_is_refused_and_a_single_tranche_ignores_it() -> None:
    with pytest.raises(ScheduleError):
        build_schedule(100, 2, date(2026, 11, 1), "WEEKLY")
    assert len(build_schedule(100, 1, date(2026, 11, 1), "MONTHLY")) == 1


def test_release_timestamps_are_midnight_utc() -> None:
    assert release_timestamp(date(1970, 1, 2)) == 86_400
    assert release_timestamp(date(2026, 10, 15)) == 1_792_022_400
    assert release_timestamp(date(2026, 10, 16)) - release_timestamp(date(2026, 10, 15)) == 86_400
