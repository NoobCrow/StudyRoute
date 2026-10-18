"""Deadline fit: the cheapest provider that ARRIVES before the due date. Pure code.

The ranking orders providers by true total cost. That is not enough when money has a deadline: the
cheapest provider can be the slowest, and money that lands after the due date means a late fee or
a rejected enrolment. Given the send date and each provider's settlement time in business days
(a day both countries work, the planner's convention), this says who arrives in time and which of
those is the cheapest.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.engine.planner import INDICATIVE, Calendar, next_business_day


class Offer(Protocol):
    """What the fit needs from a provider result: who it is and how long it takes."""

    provider_id: str
    eta_business_days: int


@dataclass(frozen=True)
class ProviderFit:
    provider_id: str
    arrives_on: date
    meets_deadline: bool
    days_to_spare: int  # calendar days between arrival and the due date; negative means late


@dataclass(frozen=True)
class DeadlineChoice:
    due_date: date
    send_date: date
    fits: tuple[ProviderFit, ...]
    best_in_time: str | None  # the cheapest provider that arrives on or before the due date
    cheapest_overall: str | None
    fastest: str | None  # the earliest arrival; ties go to the cheaper provider

    @property
    def cheapest_misses_deadline(self) -> bool:
        return self.cheapest_overall is not None and self.cheapest_overall != self.best_in_time

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "due_date": self.due_date.isoformat(),
            "send_date": self.send_date.isoformat(),
            "best_in_time": self.best_in_time,
            "cheapest_overall": self.cheapest_overall,
            "cheapest_misses_deadline": self.cheapest_misses_deadline,
            "fastest": self.fastest,
            "providers": [
                {
                    "provider_id": fit.provider_id,
                    "arrives_on": fit.arrives_on.isoformat(),
                    "meets_deadline": fit.meets_deadline,
                    "days_to_spare": fit.days_to_spare,
                }
                for fit in self.fits
            ],
            "indicative": INDICATIVE,
        }


def add_business_days(start: date, steps: int, calendars: Sequence[Calendar]) -> date:
    """Move forward `steps` business days from a day that is itself a business day."""
    if steps < 0:
        raise ValueError("The number of business days cannot be negative.")
    cursor = start
    for _ in range(steps):
        cursor = next_business_day(cursor, calendars)
    return cursor


def choose_for_deadline(
    ranked: Sequence[Offer],
    *,
    send_date: date,
    due_date: date,
    calendars: Sequence[Calendar],
) -> DeadlineChoice:
    """`ranked` is cheapest first (the engine's ranking); the first one in time is the pick."""
    fits = []
    for offer in ranked:
        arrives = add_business_days(send_date, offer.eta_business_days, calendars)
        fits.append(
            ProviderFit(
                provider_id=offer.provider_id,
                arrives_on=arrives,
                meets_deadline=arrives <= due_date,
                days_to_spare=(due_date - arrives).days,
            )
        )
    in_time = next((fit.provider_id for fit in fits if fit.meets_deadline), None)
    fastest = min(fits, key=lambda fit: fit.arrives_on).provider_id if fits else None
    return DeadlineChoice(
        due_date=due_date,
        send_date=send_date,
        fits=tuple(fits),
        best_in_time=in_time,
        cheapest_overall=fits[0].provider_id if fits else None,
        fastest=fastest,
    )
