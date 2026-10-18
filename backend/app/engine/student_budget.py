"""F21 student budget: what a month costs in a city, and which cities fit a monthly budget.

Pure arithmetic over figures that come from config (never from code). Every amount is an integer
of minor units with a currency code. A month in a city is converted to taka with the synthetic
mid-market rate and rounded UP, so the figure never promises a parent less than the month needs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from app.engine import fx
from app.engine.money import Money

HOUSING_KINDS = ("shared", "studio")
HOUSING_LABELS = {"shared": "A room in a shared flat", "studio": "Your own studio"}
LINE_LABELS = {
    "rent": "Rent",
    "food": "Food and groceries",
    "transport": "Transport",
    "utilities": "Bills (energy and water)",
    "phone_internet": "Phone and internet",
    "other": "Study materials and leisure",
}
_ONE_DECIMAL = Decimal("0.1")


@dataclass(frozen=True)
class CostLine:
    key: str
    label: str
    amount: Money


@dataclass(frozen=True)
class CityCosts:
    """What a month costs in one city, in that country's own currency."""

    country: str
    city: str
    currency: str
    rent_shared: Money
    rent_studio: Money
    food: Money
    transport: Money
    utilities: Money
    phone_internet: Money
    other: Money

    def __post_init__(self) -> None:
        for amount in self._amounts():
            if amount.currency != self.currency:
                raise ValueError(
                    f"Every amount of {self.city} must use its currency {self.currency}."
                )

    def _amounts(self) -> tuple[Money, ...]:
        return (
            self.rent_shared,
            self.rent_studio,
            self.food,
            self.transport,
            self.utilities,
            self.phone_internet,
            self.other,
        )


@dataclass(frozen=True)
class CityBudget:
    """One month in one city for one kind of housing, in local money and in taka."""

    costs: CityCosts
    housing: str
    lines: tuple[CostLine, ...]
    total: Money
    rate: Decimal
    total_bdt: Money
    rent_bdt: Money


@dataclass(frozen=True)
class CityMatch:
    """A city's month set against a monthly budget in taka (or against none)."""

    budget: CityBudget
    fits: bool | None
    spare_bdt: Money | None
    gap_bdt: Money | None

    def to_api_dict(self) -> dict[str, Any]:
        b = self.budget
        return {
            "country": b.costs.country,
            "city": b.costs.city,
            "currency": b.costs.currency,
            "housing": b.housing,
            "lines": [
                {"key": line.key, "label": line.label, **line.amount.to_dict()} for line in b.lines
            ],
            "total": b.total.to_dict(),
            "rent_share_pct": rent_share_pct(b),
            "rate_bdt_per_unit": str(b.rate),
            "total_bdt": b.total_bdt.to_dict(),
            "rent_bdt": b.rent_bdt.to_dict(),
            "fits": self.fits,
            "spare_bdt": self.spare_bdt.to_dict() if self.spare_bdt else None,
            "gap_bdt": self.gap_bdt.to_dict() if self.gap_bdt else None,
        }


def _check_housing(housing: str) -> None:
    if housing not in HOUSING_KINDS:
        raise ValueError(f"Unknown housing: {housing}. Use one of {', '.join(HOUSING_KINDS)}.")


def monthly_lines(costs: CityCosts, housing: str) -> tuple[CostLine, ...]:
    """The month as lines, rent first. Only the rent depends on the kind of housing."""
    _check_housing(housing)
    rent = costs.rent_shared if housing == "shared" else costs.rent_studio
    amounts = {
        "rent": rent,
        "food": costs.food,
        "transport": costs.transport,
        "utilities": costs.utilities,
        "phone_internet": costs.phone_internet,
        "other": costs.other,
    }
    return tuple(CostLine(key, LINE_LABELS[key], amounts[key]) for key in LINE_LABELS)


def monthly_total(costs: CityCosts, housing: str) -> Money:
    lines = monthly_lines(costs, housing)
    return Money(sum(line.amount.amount_minor for line in lines), costs.currency)


def _to_bdt_rounded_up(amount: Money, rate: Decimal) -> Money:
    exact = fx.foreign_to_bdt_minor(amount.amount_minor, amount.currency, rate)
    return Money(int(exact.to_integral_value(rounding=ROUND_CEILING)), fx.BDT)


def budget_for(costs: CityCosts, housing: str, rate: Decimal) -> CityBudget:
    lines = monthly_lines(costs, housing)
    total = monthly_total(costs, housing)
    return CityBudget(
        costs=costs,
        housing=housing,
        lines=lines,
        total=total,
        rate=rate,
        total_bdt=_to_bdt_rounded_up(total, rate),
        rent_bdt=_to_bdt_rounded_up(lines[0].amount, rate),
    )


def rent_share_pct(budget: CityBudget) -> str:
    """Rent as a share of the month, one decimal place, for example 53.0."""
    share = Decimal(budget.lines[0].amount.amount_minor) * 100 / Decimal(budget.total.amount_minor)
    return str(share.quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP))


def match_cities(budgets: Sequence[CityBudget], budget_bdt: Money | None) -> list[CityMatch]:
    """Every city from the cheapest month in taka up, each marked as fitting the budget or not.

    A month that costs exactly the budget fits. Ties in taka are ordered by country, then city,
    so the list never changes order between two requests.
    """
    if budget_bdt is not None and budget_bdt.currency != fx.BDT:
        raise ValueError("The monthly budget must be in BDT.")
    ordered = sorted(
        budgets, key=lambda b: (b.total_bdt.amount_minor, b.costs.country, b.costs.city)
    )
    rows: list[CityMatch] = []
    for budget in ordered:
        if budget_bdt is None:
            rows.append(CityMatch(budget, None, None, None))
            continue
        difference = budget_bdt.amount_minor - budget.total_bdt.amount_minor
        rows.append(
            CityMatch(
                budget,
                fits=difference >= 0,
                spare_bdt=Money(difference, fx.BDT) if difference >= 0 else None,
                gap_bdt=Money(-difference, fx.BDT) if difference < 0 else None,
            )
        )
    return rows
