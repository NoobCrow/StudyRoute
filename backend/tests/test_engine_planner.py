"""Deadline planner (blueprint 6.6). T21 covers weekends and holidays in both countries."""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.engine.money import EngineError
from app.engine.planner import (
    Calendar,
    PlannerParams,
    PlanStatus,
    is_business_day,
    parse_weekdays,
    plan_deadline,
)

BD = Calendar(
    "BD",
    parse_weekdays(["Fri", "Sat"]),
    {date(2026, 12, 16): "Victory Day", date(2026, 12, 25): "Christmas Day"},
)
GB = Calendar(
    "GB",
    parse_weekdays(["Sat", "Sun"]),
    {date(2026, 12, 25): "Christmas Day", date(2026, 12, 28): "Boxing Day (substitute)"},
)
CALENDARS = [BD, GB]
PARAMS = PlannerParams(settlement_business_days=3, buffer_days=2, cutoff=time(15, 0))
# 2026-10-14 is a Wednesday. 05:00 UTC is 11:00 in Dhaka (before the 15:00 cut-off).
MORNING = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)


def plan(due: date, now: datetime = MORNING, params: PlannerParams = PARAMS):
    return plan_deadline(due_date=due, now=now, calendars=CALENDARS, params=params)


def test_latest_send_date_steps_back_settlement_plus_buffer_business_days() -> None:
    result = plan(date(2026, 10, 28))
    assert result.latest_send_date == date(2026, 10, 20)
    assert result.recommended_send_date == date(2026, 10, 19)
    assert result.latest_send_date_without_buffer == date(2026, 10, 22)


def test_T21_due_date_on_a_bangladesh_weekend_skips_non_business_days() -> None:
    result = plan(date(2026, 10, 30))
    assert result.due_date.weekday() == 4
    assert result.latest_send_date == date(2026, 10, 22)
    skipped = {s.day: s.reasons for s in result.skipped_days}
    assert skipped[date(2026, 10, 23)] == ("BD weekend",)
    assert skipped[date(2026, 10, 25)] == ("GB weekend",)
    assert set(skipped[date(2026, 10, 24)]) == {"BD weekend", "GB weekend"}


def test_T21_uk_holiday_inside_the_window_is_skipped_and_warned() -> None:
    result = plan(date(2026, 12, 29))
    assert result.latest_send_date == date(2026, 12, 17)
    skipped = {s.day: s.reasons for s in result.skipped_days}
    assert any("Boxing Day" in reason for reason in skipped[date(2026, 12, 28)])
    assert "HOLIDAY_OVERLAP" in {w.code for w in result.warnings}


def test_due_date_that_is_itself_a_weekend_still_gives_a_business_day() -> None:
    result = plan(date(2026, 10, 24))
    assert result.latest_send_date == date(2026, 10, 15)


def test_zero_steps_moves_a_non_business_due_date_back() -> None:
    params = PlannerParams(settlement_business_days=0, buffer_days=0, cutoff=time(15, 0))
    assert plan(date(2026, 10, 24), params=params).latest_send_date == date(2026, 10, 22)
    assert plan(date(2026, 10, 22), params=params).latest_send_date == date(2026, 10, 22)


def test_latest_send_date_is_always_a_business_day_in_both_calendars() -> None:
    start = date(2026, 10, 1)
    for offset in range(120):
        due = start + timedelta(days=offset)
        result = plan(due)
        assert is_business_day(result.latest_send_date, CALENDARS)
        assert is_business_day(result.recommended_send_date, CALENDARS)
        assert result.latest_send_date < due
        counted = sum(
            1
            for d in (result.latest_send_date + timedelta(days=n) for n in range(400))
            if d < due and is_business_day(d, CALENDARS)
        )
        assert counted == 5, due


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 14, 5, 0, tzinfo=UTC), date(2026, 10, 14)),
        (datetime(2026, 10, 14, 10, 0, tzinfo=UTC), date(2026, 10, 15)),
        (datetime(2026, 10, 15, 9, 30, tzinfo=UTC), date(2026, 10, 19)),
        (datetime(2026, 10, 16, 5, 0, tzinfo=UTC), date(2026, 10, 19)),
        (datetime(2026, 10, 14, 9, 0, tzinfo=UTC), date(2026, 10, 14)),
    ],
)
def test_after_cutoff_counts_as_the_next_business_day(now: datetime, expected: date) -> None:
    assert plan(date(2026, 11, 20), now=now).earliest_send_date == expected


@pytest.mark.parametrize(
    ("now", "status"),
    [
        (datetime(2026, 10, 14, 5, 0, tzinfo=UTC), PlanStatus.ON_TRACK),
        (datetime(2026, 10, 19, 5, 0, tzinfo=UTC), PlanStatus.ON_TRACK),
        (datetime(2026, 10, 19, 10, 0, tzinfo=UTC), PlanStatus.TIGHT),
        (datetime(2026, 10, 21, 5, 0, tzinfo=UTC), PlanStatus.AT_RISK),
        (datetime(2026, 10, 22, 5, 0, tzinfo=UTC), PlanStatus.AT_RISK),
        (datetime(2026, 10, 22, 10, 0, tzinfo=UTC), PlanStatus.LATE),
    ],
)
def test_status_reflects_how_much_time_is_left(now: datetime, status: PlanStatus) -> None:
    assert plan(date(2026, 10, 28), now=now).status is status


def test_weekend_only_window_has_no_holiday_warning() -> None:
    codes = {w.code for w in plan(date(2026, 10, 28)).warnings}
    assert "HOLIDAY_OVERLAP" not in codes


def test_parse_weekdays_is_case_insensitive_and_strict() -> None:
    assert parse_weekdays(["fri", "SAT"]) == frozenset({4, 5})
    with pytest.raises(ValueError):
        parse_weekdays(["Funday"])


def test_calendar_that_never_has_a_business_day_is_an_error() -> None:
    broken = Calendar("XX", frozenset(range(7)), {})
    with pytest.raises(EngineError):
        plan_deadline(due_date=date(2026, 10, 28), now=MORNING, calendars=[broken], params=PARAMS)


def test_api_dict_is_json_ready() -> None:
    body = plan(date(2026, 10, 28)).to_api_dict()
    assert body["latest_send_date"] == "2026-10-20"
    assert body["status"] == "ON_TRACK"
    assert isinstance(body["skipped_days"], list)
    assert body["indicative"] == "Indicative. Confirm with your AD bank."
