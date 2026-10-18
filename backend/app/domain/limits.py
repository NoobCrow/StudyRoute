"""Sandbox caps (config-driven, never a statement about what is legal)."""

from __future__ import annotations

from app.domain.rules import Rules
from app.engine import fx
from app.engine.money import Money, round_half_up

PER_TRANSACTION_CAP = "PER_TRANSACTION_CAP"
DAILY_CAP = "DAILY_CAP"


def usd_equivalent_minor(rules: Rules, amount: Money) -> int:
    """USD minor units, converted through BDT with the synthetic mid-market rates."""
    if amount.currency == "USD":
        return amount.amount_minor
    bdt = round_half_up(
        fx.foreign_to_bdt_minor(
            amount.amount_minor, amount.currency, rules.mid_rate(amount.currency)
        )
    )
    return round_half_up(fx.bdt_to_foreign_minor(bdt, "USD", rules.mid_rate("USD")))


def evaluate_limits(rules: Rules, usd_minor: int, used_today_usd_minor: int) -> str | None:
    """Return which sandbox cap would be exceeded, or None."""
    if usd_minor > rules.per_transaction_limit_usd * 100:
        return PER_TRANSACTION_CAP
    if used_today_usd_minor + usd_minor > rules.daily_limit_usd * 100:
        return DAILY_CAP
    return None
