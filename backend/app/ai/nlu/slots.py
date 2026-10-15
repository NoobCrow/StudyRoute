"""Read the values out of the spans the model marked. Deterministic, no model involved."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date

from app.ai.nlu import normalize


@dataclass(frozen=True)
class Span:
    label: str  # one of schema.SLOTS
    start: int  # character range in the message
    end: int
    text: str


@dataclass
class SlotValues:
    amount_minor: int | None = None
    currency: str | None = None
    due_date: date | None = None
    months: int | None = None
    charge: str | None = None
    purpose: str | None = None
    providers: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # spans that could not be read as a value

    def as_dict(self) -> dict[str, object]:
        return {
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "months": self.months,
            "charge": self.charge,
            "purpose": self.purpose,
            "providers": self.providers,
        }


def _distance(a: Span, b: Span) -> int:
    if a.end <= b.start:
        return b.start - a.end
    if b.end <= a.start:
        return a.start - b.end
    return 0


def _amount_and_currency(
    spans: Sequence[Span], supported: Collection[str], values: SlotValues
) -> None:
    amounts = [s for s in spans if s.label == "AMOUNT"]
    currencies = [s for s in spans if s.label == "CURRENCY"]
    for amount in amounts:
        value = normalize.parse_amount(amount.text)
        if value is None:
            values.problems.append(f"AMOUNT:{amount.text}")
            continue
        ranked = sorted(currencies, key=lambda c: _distance(amount, c))
        for currency in ranked:
            code = normalize.parse_currency(currency.text, supported)
            if code is None:
                continue
            minor = normalize.to_minor(value, code)
            if minor is not None:
                values.amount_minor, values.currency = minor, code
                return
        if not ranked:
            continue  # an amount with no currency: the assistant will ask for it
        values.problems.append(f"CURRENCY:{ranked[0].text}")
    return


def read_slots(spans: Sequence[Span], today: date, supported: Collection[str]) -> SlotValues:
    """Turn marked spans into typed values. Anything unreadable is listed in ``problems``."""
    values = SlotValues()
    _amount_and_currency(spans, supported, values)
    for span in spans:
        if span.label == "DATE" and values.due_date is None:
            values.due_date = normalize.parse_date(span.text, today)
            if values.due_date is None:
                values.problems.append(f"DATE:{span.text}")
        elif span.label == "DURATION" and values.months is None:
            values.months = normalize.parse_duration_months(span.text)
            if values.months is None:
                values.problems.append(f"DURATION:{span.text}")
        elif span.label == "CHARGE" and values.charge is None:
            values.charge = normalize.parse_charge(span.text)
        elif span.label == "PURPOSE" and values.purpose is None:
            values.purpose = normalize.parse_purpose(span.text)
        elif span.label == "PROVIDER":
            provider = normalize.parse_provider(span.text)
            if provider and provider not in values.providers:
                values.providers.append(provider)
    return values
