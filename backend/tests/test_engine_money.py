"""Money type: integer minor units, Decimal rounding, no floats."""

from decimal import Decimal

import pytest

from app.engine.money import InvalidAmount, Money, UnsupportedCurrency, round_half_up


def test_money_holds_integer_minor_units_and_a_currency() -> None:
    money = Money(1_000_000, "GBP")
    assert money.amount_minor == 1_000_000
    assert money.currency == "GBP"
    assert money.format() == "GBP 10,000.00"


def test_money_rejects_floats_and_booleans() -> None:
    with pytest.raises(TypeError):
        Money(10.5, "GBP")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        Money(True, "GBP")  # type: ignore[arg-type]


def test_money_rejects_unknown_currency() -> None:
    with pytest.raises(UnsupportedCurrency):
        Money(100, "XXX")


def test_from_major_rounds_half_up_not_bankers_and_not_binary_float() -> None:
    assert Money.from_major(Decimal("0.005"), "GBP").amount_minor == 1
    assert Money.from_major(Decimal("1.004"), "GBP").amount_minor == 100
    assert Money.from_major("2.675", "USD").amount_minor == 268
    assert Money.from_major("0.025", "USD").amount_minor == 3


def test_from_major_refuses_floats() -> None:
    with pytest.raises(TypeError):
        Money.from_major(1.1, "GBP")  # type: ignore[arg-type]


def test_zero_decimal_currency_uses_exponent_zero() -> None:
    assert Money.from_major("1500", "JPY").amount_minor == 1500
    assert Money(1500, "JPY").format() == "JPY 1,500"


def test_formatting_negative_and_large_amounts() -> None:
    assert Money(-250, "BDT").format() == "-BDT 2.50"
    assert Money(162_530_000, "BDT").format() == "BDT 1,625,300.00"
    assert Money(5, "USD").format() == "USD 0.05"


def test_arithmetic_requires_matching_currency() -> None:
    assert (Money(100, "GBP") + Money(250, "GBP")).amount_minor == 350
    assert (Money(500, "GBP") - Money(250, "GBP")).amount_minor == 250
    with pytest.raises(ValueError):
        _ = Money(100, "GBP") + Money(100, "USD")


def test_require_positive() -> None:
    assert Money(1, "GBP").require_positive().amount_minor == 1
    with pytest.raises(InvalidAmount):
        Money(0, "GBP").require_positive()
    with pytest.raises(InvalidAmount):
        Money(-5, "GBP").require_positive()


def test_to_dict_is_json_ready() -> None:
    assert Money(1_000_000, "GBP").to_dict() == {
        "amount_minor": 1_000_000,
        "currency": "GBP",
        "formatted": "GBP 10,000.00",
    }


def test_round_half_up_helper() -> None:
    assert round_half_up(Decimal("2.5")) == 3
    assert round_half_up(Decimal("-2.5")) == -3
    assert round_half_up(Decimal("2.4999")) == 2
