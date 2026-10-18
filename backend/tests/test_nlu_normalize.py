"""The deterministic half of the trained reader: spans of the person's words become typed values.

The model only marks words; this code decides what they mean. A span it cannot read gives None
(the assistant then asks), never a guess. Today in these tests is Thursday 15 October 2026.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.ai.nlu import normalize
from app.ai.nlu.slots import Span, read_slots

TODAY = date(2026, 10, 15)
CURRENCIES = {"GBP", "USD", "EUR", "AUD", "CAD", "MYR", "JPY", "BDT", "ALL", "TRY"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10,000", "10000"),
        ("10000", "10000"),
        ("10k", "10000"),
        ("10.5k", "10500"),
        ("10 k", "10000"),
        ("ten thousand", "10000"),
        ("twelve hundred", "1200"),
        ("twelve thousand five hundred", "12500"),
        ("ten grand", "10000"),
        ("1.5 lakh", "150000"),
        ("2 lakh", "200000"),
        ("two lakh fifty thousand", "250000"),
        ("2 crore", "20000000"),
        ("1,00,000", "100000"),
        ("12,50,000", "1250000"),
        ("3m", "3000000"),
        ("2.5 million", "2500000"),
        ("10 000", "10000"),
        ("£10,000", "10000"),
        ("a hundred", "100"),
        ("5,000.50", "5000.50"),
    ],
)
def test_amounts_are_read_exactly(text: str, expected: str) -> None:
    assert normalize.parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "abc", "0", "1,5", "1,0000", "10,00", "ten banana", "k"])
def test_an_amount_that_cannot_be_read_exactly_is_refused_not_guessed(text: str) -> None:
    assert normalize.parse_amount(text) is None


def test_money_is_integer_minor_units_and_bounded() -> None:
    assert normalize.to_minor(Decimal("10000"), "GBP") == 1_000_000
    assert normalize.to_minor(Decimal("5000.50"), "USD") == 500_050
    assert normalize.to_minor(Decimal("125000"), "JPY") == 125_000  # yen has no minor unit
    assert normalize.to_minor(Decimal("0"), "GBP") is None
    assert normalize.to_minor(Decimal("10"), "NOPE") is None
    assert normalize.to_minor(Decimal("10") ** 12, "GBP") is None


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("GBP", "GBP"),
        ("gbp", "GBP"),
        ("£", "GBP"),
        ("pounds", "GBP"),
        ("quid", "GBP"),
        ("pounds sterling", "GBP"),
        ("€", "EUR"),
        ("euros", "EUR"),
        ("$", "USD"),
        ("US dollars", "USD"),
        ("Australian dollars", "AUD"),
        ("AUD dollars", "AUD"),
        ("A$", "AUD"),
        ("C$", "CAD"),
        ("RM", "MYR"),
        ("ringgit", "MYR"),
        ("taka", "BDT"),
        ("yen", "JPY"),
    ],
)
def test_currencies(text: str, code: str) -> None:
    assert normalize.parse_currency(text, CURRENCIES) == code


def test_a_word_that_is_also_a_currency_code_only_counts_in_capitals() -> None:
    assert normalize.parse_currency("all", CURRENCIES) is None
    assert normalize.parse_currency("try", CURRENCIES) is None
    assert normalize.parse_currency("ALL", CURRENCIES) == "ALL"


def test_a_currency_the_sandbox_does_not_serve_is_refused() -> None:
    assert normalize.parse_currency("xyz", CURRENCIES) is None
    assert normalize.parse_currency("GBP", {"USD"}) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("28 October", date(2026, 10, 28)),
        ("28th Oct", date(2026, 10, 28)),
        ("Oct 28", date(2026, 10, 28)),
        ("28/10/2026", date(2026, 10, 28)),
        ("2026-10-28", date(2026, 10, 28)),
        ("the 20th of November", date(2026, 11, 20)),
        ("first of December", date(2026, 12, 1)),
        ("twenty eighth of october", date(2026, 10, 28)),
        ("the 28th", date(2026, 10, 28)),
        ("the 12th", date(2026, 11, 12)),  # the 12th of this month has passed
        ("end of October", date(2026, 10, 31)),
        ("end of February", date(2027, 2, 28)),
        ("mid November", date(2026, 11, 15)),
        ("28th of next month", date(2026, 11, 28)),
        ("tomorrow", date(2026, 10, 16)),
        ("day after tomorrow", date(2026, 10, 17)),
        ("in 3 weeks", date(2026, 11, 5)),
        ("in three weeks", date(2026, 11, 5)),
        ("in a fortnight", date(2026, 10, 29)),
        ("in 2 months", date(2026, 12, 15)),
        ("friday", date(2026, 10, 16)),
        ("next Friday", date(2026, 10, 23)),
        ("Monday", date(2026, 10, 19)),
    ],
)
def test_dates(text: str, expected: date) -> None:
    assert normalize.parse_date(text, TODAY) == expected


@pytest.mark.parametrize("text", ["next month", "by next week", "soon", "31 February", "someday"])
def test_a_date_that_is_not_exact_is_refused(text: str) -> None:
    assert normalize.parse_date(text, TODAY) is None


@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("9 months", 9),
        ("nine months", 9),
        ("a year", 12),
        ("one year", 12),
        ("the academic year", 12),
        ("for 2 years", 24),
        ("the next 8 months", 8),
    ],
)
def test_durations(text: str, months: int) -> None:
    assert normalize.parse_duration_months(text) == months


def test_a_duration_outside_five_years_is_refused() -> None:
    assert normalize.parse_duration_months("100 months") is None


def test_charge_purpose_and_provider() -> None:
    assert normalize.parse_charge("with OUR charges") == "OUR"
    assert normalize.parse_charge("sha") == "SHA"
    assert normalize.parse_charge("nothing here") is None
    assert normalize.parse_purpose("living costs") == "LIVING"
    assert normalize.parse_purpose("tuition fees") == "TUITION"
    assert normalize.parse_purpose("hello") is None
    assert normalize.parse_provider("Provider B") == "prov_b"
    assert normalize.parse_provider("prov_c") == "prov_c"
    assert normalize.parse_provider("a") == "prov_a"
    assert normalize.parse_provider("about") is None


def _spans(text: str, *marks: tuple[str, str]) -> list[Span]:
    spans = []
    for label, piece in marks:
        start = text.index(piece)
        spans.append(Span(label, start, start + len(piece), piece))
    return spans


def test_slots_pair_each_amount_with_the_nearest_currency() -> None:
    text = "send 800 GBP a month, not 90 USD"
    values = read_slots(
        _spans(text, ("AMOUNT", "800"), ("CURRENCY", "GBP"), ("CURRENCY", "USD")), TODAY, CURRENCIES
    )
    assert (values.amount_minor, values.currency) == (80_000, "GBP")
    assert values.problems == []


def test_slots_use_the_first_amount_that_can_be_read() -> None:
    text = "1,5 or GBP 900"
    values = read_slots(
        _spans(text, ("AMOUNT", "1,5"), ("AMOUNT", "900"), ("CURRENCY", "GBP")), TODAY, CURRENCIES
    )
    assert (values.amount_minor, values.currency) == (90_000, "GBP")
    assert "AMOUNT:1,5" in values.problems


def test_slots_keep_an_unreadable_value_out_and_say_so() -> None:
    text = "due someday for 9 months with BEN"
    values = read_slots(
        _spans(text, ("DATE", "someday"), ("DURATION", "9 months"), ("CHARGE", "BEN")),
        TODAY,
        CURRENCIES,
    )
    assert values.due_date is None
    assert values.problems == ["DATE:someday"]
    assert (values.months, values.charge) == (9, "BEN")
    assert values.as_dict()["due_date"] is None
