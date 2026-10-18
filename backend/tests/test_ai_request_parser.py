"""Reading "I need to pay GBP 10,000 by 28 October" without a model: exact, never a float."""

from __future__ import annotations

from datetime import date

import pytest

from app.ai.request_parser import parse_request

TODAY = date(2026, 10, 14)
CURRENCIES = {"GBP", "USD", "EUR", "AUD", "CAD", "MYR"}


def parse(message: str):
    return parse_request(message, CURRENCIES, TODAY)


def test_amount_currency_purpose_and_due_date_from_one_sentence() -> None:
    got = parse("I need to pay GBP 10,000 tuition by 28 October")
    assert (got.amount_minor, got.currency) == (1_000_000, "GBP")
    assert got.due_date == date(2026, 10, 28)
    assert got.purpose == "TUITION"
    assert got.charge_code == "OUR"


@pytest.mark.parametrize(
    ("message", "minor", "currency"),
    [
        ("Plan 10,000 GBP for fees", 1_000_000, "GBP"),
        ("plan gbp 10000", 1_000_000, "GBP"),
        ("Plan £10,000 for the autumn fees", 1_000_000, "GBP"),
        ("USD25000.50 please", 2_500_050, "USD"),
        ("I need 10k EUR", 1_000_000, "EUR"),
        ("GBP 10,000.5", 1_000_050, "GBP"),
        ("send 1,200 pounds a month", 120_000, "GBP"),
        ("2,500 euros for rent", 250_000, "EUR"),
        ("MYR 800", 80_000, "MYR"),
    ],
)
def test_amounts_are_read_exactly_in_minor_units(message: str, minor: int, currency: str) -> None:
    got = parse(message)
    assert (got.amount_minor, got.currency) == (minor, currency)


@pytest.mark.parametrize(
    "message",
    [
        "when should I send?",
        "Why is B cheaper than A?",
        "10,000 JPY",
        "GBP 99999999999999",
        "I have 10,000 problems",
        "pay SHA now",
    ],
)
def test_no_amount_is_invented_when_there_is_none(message: str) -> None:
    got = parse(message)
    assert got.amount_minor is None and got.currency is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("GBP 5,000 due 2026-12-01", date(2026, 12, 1)),
        ("GBP 5,000 due 3 Nov 2026", date(2026, 11, 3)),
        ("GBP 5,000 by November 3rd", date(2026, 11, 3)),
        ("GBP 5,000 by 5th of January", date(2027, 1, 5)),
        ("GBP 5,000 by Sept 20", date(2027, 9, 20)),
        ("GBP 5,000 due 12/11/2026", date(2026, 11, 12)),
        ("GBP 5,000 in 3 weeks", date(2026, 11, 4)),
        ("GBP 5,000 in 10 days", date(2026, 10, 24)),
    ],
)
def test_due_dates_in_the_ways_people_write_them(message: str, expected: date) -> None:
    assert parse(message).due_date == expected


def test_impossible_dates_are_ignored_not_guessed() -> None:
    assert parse("GBP 5,000 by 31 February").due_date is None
    assert parse("GBP 5,000 by 45 October").due_date is None


def test_living_costs_and_monthly_amounts() -> None:
    got = parse("How often should I send 800 GBP a month for living costs for 9 months?")
    assert (got.amount_minor, got.currency) == (80_000, "GBP")
    assert got.per_month is True and got.months == 9
    assert got.purpose == "LIVING"
    assert parse("send GBP 1,000 monthly for a year").months == 12
    assert parse("GBP 12,000 for the academic year").months == 12
    assert parse("GBP 5,000 tuition").per_month is False


def test_the_charge_code_is_read_and_defaults_to_our() -> None:
    assert parse("GBP 5,000 with SHA charges").charge_code == "SHA"
    assert parse("GBP 5,000 with ben charges").charge_code == "BEN"
    assert parse("GBP 5,000, my friend ben says hi").charge_code == "OUR"
    assert parse("GBP 5,000").charge_code == "OUR"
