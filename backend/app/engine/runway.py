"""F9 living-cost runway: how many months does the amount sent cover? Pure arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.engine.money import Money

_ONE_DECIMAL = Decimal("0.1")


@dataclass(frozen=True)
class Runway:
    amount: Money
    monthly_cost: Money
    full_months: int
    covers_months: Decimal
    leftover: Money

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "amount": self.amount.to_dict(),
            "monthly_cost": self.monthly_cost.to_dict(),
            "full_months": self.full_months,
            "covers_months": str(self.covers_months),
            "leftover": self.leftover.to_dict(),
            "display": {
                "amount": self.amount.format(),
                "monthly_cost": self.monthly_cost.format(),
                "covers": f"{self.covers_months} months",
                "full_months": f"{self.full_months} full months",
                "leftover": self.leftover.format(),
            },
        }


def compute_runway(amount: Money, monthly_cost: Money) -> Runway:
    """Whole months plus a one-decimal figure that is rounded DOWN, so it never over-promises."""
    if amount.currency != monthly_cost.currency:
        raise ValueError("Amount and monthly cost must use the same currency.")
    amount.require_positive()
    monthly_cost.require_positive()
    full, left = divmod(amount.amount_minor, monthly_cost.amount_minor)
    covers = (Decimal(amount.amount_minor) / Decimal(monthly_cost.amount_minor)).quantize(
        _ONE_DECIMAL, rounding=ROUND_DOWN
    )
    return Runway(amount, monthly_cost, full, covers, Money(left, amount.currency))
