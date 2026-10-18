"""F21 student budget (pure engine): the cost of a month in a city and which cities fit a budget."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.money import Money
from app.engine.student_budget import (
    CityCosts,
    budget_for,
    match_cities,
    monthly_lines,
    monthly_total,
    rent_share_pct,
)


def gbp(major: int) -> Money:
    return Money.from_major(major, "GBP")


def london() -> CityCosts:
    return CityCosts(
        country="GB",
        city="London",
        currency="GBP",
        rent_shared=gbp(850),
        rent_studio=gbp(1500),
        food=gbp(280),
        transport=gbp(160),
        utilities=gbp(90),
        phone_internet=gbp(25),
        other=gbp(200),
    )


def leeds() -> CityCosts:
    return CityCosts(
        country="GB",
        city="Leeds",
        currency="GBP",
        rent_shared=gbp(500),
        rent_studio=gbp(800),
        food=gbp(230),
        transport=gbp(60),
        utilities=gbp(70),
        phone_internet=gbp(25),
        other=gbp(160),
    )


RATE = Decimal("160.000000")


def test_the_lines_add_up_to_the_total_and_name_the_rent_first() -> None:
    lines = monthly_lines(london(), "shared")
    assert [line.key for line in lines] == [
        "rent",
        "food",
        "transport",
        "utilities",
        "phone_internet",
        "other",
    ]
    total = monthly_total(london(), "shared")
    assert total == gbp(850 + 280 + 160 + 90 + 25 + 200)
    assert sum(line.amount.amount_minor for line in lines) == total.amount_minor


def test_a_studio_changes_only_the_rent() -> None:
    shared, studio = monthly_total(london(), "shared"), monthly_total(london(), "studio")
    assert studio - shared == gbp(1500 - 850)
    assert monthly_lines(london(), "studio")[0].amount == gbp(1500)
    assert monthly_lines(london(), "studio")[1:] == monthly_lines(london(), "shared")[1:]


def test_an_unknown_kind_of_housing_is_refused() -> None:
    with pytest.raises(ValueError, match="housing"):
        monthly_total(london(), "castle")


def test_the_taka_figure_is_exact_when_the_rate_divides_evenly() -> None:
    budget = budget_for(london(), "shared", RATE)
    assert budget.total == gbp(1605)
    assert budget.total_bdt == Money.from_major(1605 * 160, "BDT")
    assert budget.rent_bdt == Money.from_major(850 * 160, "BDT")


def test_the_taka_figure_rounds_up_so_it_never_promises_too_little() -> None:
    # GBP 1,605.00 at 163.333333 BDT per GBP is 262,150.00 (rounded up from 262,149.99...).
    rate = Decimal("163.333333")
    budget = budget_for(london(), "shared", rate)
    exact = Decimal(160_500) * rate  # in poisha: 160,500 pence * rate * (100 / 100)
    assert budget.total_bdt.amount_minor >= exact
    assert budget.total_bdt.amount_minor - exact < 1
    assert budget.total_bdt.currency == "BDT"


def test_rent_is_shown_as_a_share_of_the_month_rounded_to_one_decimal() -> None:
    budget = budget_for(london(), "shared", RATE)
    assert rent_share_pct(budget) == "53.0"  # 850 / 1605 = 52.96...


def test_a_budget_that_equals_the_total_fits_and_one_poisha_less_does_not() -> None:
    budget = budget_for(leeds(), "shared", RATE)
    on_the_line = match_cities([budget], budget.total_bdt)[0]
    assert on_the_line.fits is True
    assert on_the_line.spare_bdt == Money(0, "BDT")
    just_short = match_cities([budget], Money(budget.total_bdt.amount_minor - 1, "BDT"))[0]
    assert just_short.fits is False
    assert just_short.gap_bdt == Money(1, "BDT")
    assert just_short.spare_bdt is None


def test_cities_are_listed_from_the_cheapest_month_in_taka() -> None:
    cities = [budget_for(london(), "shared", RATE), budget_for(leeds(), "shared", RATE)]
    ordered = match_cities(cities, Money.from_major(170_000, "BDT"))
    assert [row.budget.costs.city for row in ordered] == ["Leeds", "London"]
    assert [row.fits for row in ordered] == [True, False]
    assert ordered[1].gap_bdt == Money.from_major(1605 * 160 - 170_000, "BDT")


def test_without_a_budget_nothing_is_judged() -> None:
    row = match_cities([budget_for(leeds(), "shared", RATE)], None)[0]
    assert row.fits is None and row.spare_bdt is None and row.gap_bdt is None


def test_a_tie_in_taka_is_broken_by_country_then_city_so_the_order_never_changes() -> None:
    a = CityCosts("AU", "Zed", "GBP", *(gbp(100),) * 7)
    b = CityCosts("AU", "Alpha", "GBP", *(gbp(100),) * 7)
    c = CityCosts("DE", "Alpha", "GBP", *(gbp(100),) * 7)
    rows = match_cities([budget_for(x, "shared", RATE) for x in (c, a, b)], None)
    assert [(r.budget.costs.country, r.budget.costs.city) for r in rows] == [
        ("AU", "Alpha"),
        ("AU", "Zed"),
        ("DE", "Alpha"),
    ]


def test_a_budget_in_another_currency_than_taka_is_refused() -> None:
    with pytest.raises(ValueError, match="BDT"):
        match_cities([budget_for(leeds(), "shared", RATE)], gbp(1000))


def test_a_city_whose_lines_use_two_currencies_is_refused() -> None:
    with pytest.raises(ValueError, match="currency"):
        CityCosts(
            "GB",
            "Mixed",
            "GBP",
            gbp(1),
            gbp(2),
            Money.from_major(3, "USD"),
            gbp(4),
            gbp(5),
            gbp(6),
            gbp(7),
        )
