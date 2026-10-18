"""Money in integer minor units plus a currency code. Never floats."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.engine.currencies import CURRENCY_EXPONENTS


class EngineError(Exception):
    """Base class for errors raised by the pure engine."""


class UnsupportedCurrency(EngineError):
    pass


class InvalidAmount(EngineError):
    pass


def exponent(currency: str) -> int:
    try:
        return CURRENCY_EXPONENTS[currency]
    except KeyError as exc:
        raise UnsupportedCurrency(f"Unsupported currency: {currency}") from exc


def round_half_up(value: Decimal) -> int:
    """Round to the nearest integer, halves away from zero."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an int (minor units), never a float")
        exponent(self.currency)

    @classmethod
    def from_major(cls, value: Decimal | str | int, currency: str) -> Money:
        if isinstance(value, bool | float):
            raise TypeError("major amounts must be Decimal, str or int, never float")
        scaled = Decimal(value) * (Decimal(10) ** exponent(currency))
        return cls(round_half_up(scaled), currency)

    def format(self) -> str:
        exp = exponent(self.currency)
        sign = "-" if self.amount_minor < 0 else ""
        digits = abs(self.amount_minor)
        if exp == 0:
            body = f"{digits:,}"
        else:
            major, minor = divmod(digits, 10**exp)
            body = f"{major:,}.{minor:0{exp}d}"
        return f"{sign}{self.currency} {body}"

    def require_positive(self) -> Money:
        if self.amount_minor <= 0:
            raise InvalidAmount("Amount must be greater than zero.")
        return self

    def _same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def to_dict(self) -> dict[str, Any]:
        return {
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "formatted": self.format(),
        }
