"""F9 living-cost runway and F10 synthetic rate history / best-day hint (pure engine)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import pairwise

import pytest

from app.engine.money import InvalidAmount, Money
from app.engine.rates import HintKind, rate_hint, synthetic_history
from app.engine.runway import compute_runway

TODAY = date(2026, 10, 14)


def test_runway_counts_whole_months_and_never_rounds_up() -> None:
    result = compute_runway(Money(1_000_000, "GBP"), Money(150_000, "GBP"))
    assert result.full_months == 6
    assert result.covers_months == Decimal("6.6")
    assert result.leftover == Money(100_000, "GBP")


def test_runway_exact_division_and_short_amount() -> None:
    exact = compute_runway(Money(900_000, "GBP"), Money(150_000, "GBP"))
    assert (exact.full_months, exact.covers_months, exact.leftover.amount_minor) == (
        6,
        Decimal("6.0"),
        0,
    )
    short = compute_runway(Money(100_000, "GBP"), Money(150_000, "GBP"))
    assert short.full_months == 0 and short.covers_months == Decimal("0.6")


def test_runway_rejects_bad_input() -> None:
    with pytest.raises(InvalidAmount):
        compute_runway(Money(1000, "GBP"), Money(0, "GBP"))
    with pytest.raises(ValueError):
        compute_runway(Money(1000, "GBP"), Money(100, "USD"))


def test_runway_api_dict_is_formatted_by_the_engine() -> None:
    body = compute_runway(Money(1_000_000, "GBP"), Money(150_000, "GBP")).to_api_dict()
    assert body["display"]["covers"] == "6.6 months"
    assert body["display"]["monthly_cost"] == "GBP 1,500.00"
    assert body["display"]["leftover"] == "GBP 1,000.00"


def test_history_is_deterministic_ends_at_the_base_rate_and_stays_in_a_band() -> None:
    base = Decimal("160.000000")
    first = synthetic_history("GBP", base, TODAY, days=30)
    again = synthetic_history("GBP", base, TODAY, days=30)
    assert first == again
    assert len(first) == 30
    assert first[-1].day == TODAY and first[-1].rate == base
    assert all(Decimal("157") <= p.rate <= Decimal("163") for p in first)
    assert len({p.rate for p in first}) > 10
    assert synthetic_history("USD", Decimal("122"), TODAY, 30)[0].rate != first[0].rate


def test_each_rate_has_six_decimals_and_dates_are_consecutive() -> None:
    points = synthetic_history("EUR", Decimal("140.000000"), TODAY, days=10)
    assert all(p.rate == p.rate.quantize(Decimal("0.000001")) for p in points)
    assert [(b.day - a.day).days for a, b in pairwise(points)] == [1] * 9


def test_the_hint_compares_today_with_the_recent_average_and_is_never_a_forecast() -> None:
    base = Decimal("160.000000")
    points = synthetic_history("GBP", base, TODAY, days=30)
    hint = rate_hint(points)
    assert hint.kind in set(HintKind)
    body = hint.to_api_dict()
    assert body["synthetic"] is True
    assert "not a forecast" in body["message"].lower()
    assert "Indicative. Confirm with your AD bank." in body["message"]
    assert body["today"] == "160.000000"


def test_hint_kinds_follow_the_gap_to_the_average() -> None:
    from app.engine.rates import RatePoint

    def series(today: str, rest: str) -> list[RatePoint]:
        points = [RatePoint(date(2026, 9, 1 + i), Decimal(rest)) for i in range(20)]
        return [*points, RatePoint(date(2026, 9, 21), Decimal(today))]

    assert rate_hint(series("99.00", "100.00")).kind is HintKind.SEND_NOW
    assert rate_hint(series("101.00", "100.00")).kind is HintKind.WAIT_MAY_HELP
    assert rate_hint(series("100.20", "100.00")).kind is HintKind.NEUTRAL
