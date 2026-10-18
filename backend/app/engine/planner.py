"""Deadline planner (blueprint 6.6). Pure code: the caller supplies "now" and the calendars.

A business day is a day that is a working day in BOTH Bangladesh and the host country.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from app.engine.money import EngineError

INDICATIVE = "Indicative. Confirm with your AD bank."
_WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_MAX_SCAN_DAYS = 400


def parse_weekdays(names: Iterable[str]) -> frozenset[int]:
    days: set[int] = set()
    for name in names:
        key = name.strip()[:3].lower()
        if key not in _WEEKDAYS or len(name.strip()) < 3:
            raise ValueError(f"Unknown weekday name: {name!r}")
        days.add(_WEEKDAYS[key])
    return frozenset(days)


@dataclass(frozen=True)
class Calendar:
    country: str
    weekend: frozenset[int]
    holidays: Mapping[date, str] = field(default_factory=dict)

    def non_business_reason(self, day: date) -> str | None:
        if day.weekday() in self.weekend:
            return f"{self.country} weekend"
        if day in self.holidays:
            return f"{self.country} holiday: {self.holidays[day]}"
        return None


@dataclass(frozen=True)
class PlannerParams:
    settlement_business_days: int
    buffer_days: int
    cutoff: time
    cutoff_tz: str = "Asia/Dhaka"


class PlanStatus(StrEnum):
    ON_TRACK = "ON_TRACK"
    TIGHT = "TIGHT"
    AT_RISK = "AT_RISK"
    LATE = "LATE"


@dataclass(frozen=True)
class SkippedDay:
    day: date
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class PlanWarning:
    code: str
    message: str


@dataclass(frozen=True)
class DeadlinePlan:
    due_date: date
    latest_send_date: date
    recommended_send_date: date
    latest_send_date_without_buffer: date
    earliest_send_date: date
    status: PlanStatus
    days_until_latest_send: int
    skipped_days: tuple[SkippedDay, ...]
    warnings: tuple[PlanWarning, ...]
    settlement_business_days: int
    buffer_days: int
    cutoff: time

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "due_date": self.due_date.isoformat(),
            "latest_send_date": self.latest_send_date.isoformat(),
            "recommended_send_date": self.recommended_send_date.isoformat(),
            "latest_send_date_without_buffer": self.latest_send_date_without_buffer.isoformat(),
            "earliest_send_date": self.earliest_send_date.isoformat(),
            "status": self.status.value,
            "days_until_latest_send": self.days_until_latest_send,
            "settlement_business_days": self.settlement_business_days,
            "buffer_days": self.buffer_days,
            "bank_cutoff_local": self.cutoff.strftime("%H:%M"),
            "skipped_days": [
                {"date": s.day.isoformat(), "reasons": list(s.reasons)} for s in self.skipped_days
            ],
            "warnings": [{"code": w.code, "message": w.message} for w in self.warnings],
            "indicative": INDICATIVE,
        }


def skip_reasons(day: date, calendars: Sequence[Calendar]) -> tuple[str, ...]:
    reasons = (calendar.non_business_reason(day) for calendar in calendars)
    return tuple(reason for reason in reasons if reason is not None)


def is_business_day(day: date, calendars: Sequence[Calendar]) -> bool:
    return not skip_reasons(day, calendars)


def _step_back(
    start: date, steps: int, calendars: Sequence[Calendar]
) -> tuple[date, list[SkippedDay]]:
    """Move back `steps` business days, always landing on a business day."""
    cursor = start
    skipped: list[SkippedDay] = []
    scanned = 0

    def retreat() -> None:
        nonlocal cursor, scanned
        cursor -= timedelta(days=1)
        scanned += 1
        if scanned > _MAX_SCAN_DAYS:
            raise EngineError("No business day found: check the calendar configuration.")

    if steps == 0:
        while reasons := skip_reasons(cursor, calendars):
            skipped.append(SkippedDay(cursor, reasons))
            retreat()
        return cursor, skipped
    for _ in range(steps):
        retreat()
        while reasons := skip_reasons(cursor, calendars):
            skipped.append(SkippedDay(cursor, reasons))
            retreat()
    return cursor, skipped


def next_business_day(day: date, calendars: Sequence[Calendar]) -> date:
    cursor = day
    for _ in range(_MAX_SCAN_DAYS):
        cursor += timedelta(days=1)
        if is_business_day(cursor, calendars):
            return cursor
    raise EngineError("No business day found: check the calendar configuration.")


def earliest_send_date(local_now: datetime, calendars: Sequence[Calendar], cutoff: time) -> date:
    """First day a payment sent now would count: after the cut-off it is the next business day."""
    today = local_now.date()
    if not is_business_day(today, calendars) or local_now.time() > cutoff:
        return next_business_day(today, calendars)
    return today


def _classify(earliest: date, recommended: date, latest: date, no_buffer: date) -> PlanStatus:
    if earliest <= recommended:
        return PlanStatus.ON_TRACK
    if earliest <= latest:
        return PlanStatus.TIGHT
    if earliest <= no_buffer:
        return PlanStatus.AT_RISK
    return PlanStatus.LATE


_STATUS_MESSAGES = {
    PlanStatus.TIGHT: (
        "STATUS_TIGHT",
        "The recommended send date has passed. You are now using the safety buffer.",
    ),
    PlanStatus.AT_RISK: (
        "STATUS_AT_RISK",
        "The safety buffer is used up. Send as early as possible.",
    ),
    PlanStatus.LATE: (
        "STATUS_LATE",
        "Too late to meet the due date with normal settlement times. Ask the university to wait.",
    ),
}


def _warnings(skipped: Sequence[SkippedDay], status: PlanStatus) -> tuple[PlanWarning, ...]:
    found: list[PlanWarning] = []
    holidays = [s for s in skipped if any("holiday" in reason for reason in s.reasons)]
    if holidays:
        listing = "; ".join(f"{s.day.isoformat()} ({', '.join(s.reasons)})" for s in holidays)
        found.append(
            PlanWarning("HOLIDAY_OVERLAP", f"Public holidays fall in the window: {listing}.")
        )
    if status in _STATUS_MESSAGES:
        code, message = _STATUS_MESSAGES[status]
        found.append(PlanWarning(code, message))
    return tuple(found)


def plan_deadline(
    *,
    due_date: date,
    now: datetime,
    calendars: Sequence[Calendar],
    params: PlannerParams,
) -> DeadlinePlan:
    """Work backwards from the university due date using both countries' working days."""
    steps = params.settlement_business_days + params.buffer_days
    latest, skipped = _step_back(due_date, steps, calendars)
    recommended, _ = _step_back(latest, 1, calendars)
    no_buffer, _ = _step_back(due_date, params.settlement_business_days, calendars)

    local_now = now.astimezone(ZoneInfo(params.cutoff_tz))
    earliest = earliest_send_date(local_now, calendars, params.cutoff)
    status = _classify(earliest, recommended, latest, no_buffer)
    return DeadlinePlan(
        due_date=due_date,
        latest_send_date=latest,
        recommended_send_date=recommended,
        latest_send_date_without_buffer=no_buffer,
        earliest_send_date=earliest,
        status=status,
        days_until_latest_send=(latest - local_now.date()).days,
        skipped_days=tuple(skipped),
        warnings=_warnings(skipped, status),
        settlement_business_days=params.settlement_business_days,
        buffer_days=params.buffer_days,
        cutoff=params.cutoff,
    )
