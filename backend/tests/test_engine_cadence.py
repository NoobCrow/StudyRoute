"""Smart send plan: the same money sent monthly, quarterly, per term or all at once.

Fixed and SWIFT fees are paid per transfer and the FX margin scales with the amount, so how
often you send changes the real cost. Hand-worked case, mid rate 160.00, charge code OUR:

    GBP 12,000 over 12 months
    monthly   12 x GBP 1,000   best A (no shortfall): 12 x BDT  5,700 = BDT  68,400
    quarterly  4 x GBP 3,000   best A:                 4 x BDT 12,100 = BDT  48,400
    termly     2 x GBP 6,000   best B:                 2 x BDT 18,900 = BDT  37,800
    upfront    1 x GBP 12,000  best B:                              BDT  28,500
"""

from decimal import Decimal

import pytest

from app.engine.cadence import plan_cadence, split_evenly
from app.engine.money import InvalidAmount, Money
from app.engine.quote import ChargeCode, EngineParams
from tests.test_engine_quote import synthetic_providers

MID = Decimal("160.000000")


def plan(total_minor: int = 1_200_000, months: int = 12, charge: ChargeCode = ChargeCode.OUR):
    return plan_cadence(
        total=Money(total_minor, "GBP"),
        months=months,
        mid_rate=MID,
        providers=synthetic_providers(),
        charge_code=charge,
        params=EngineParams(),
    )


def option(result, key: str):
    return next(o for o in result.options if o.key == key)


def test_the_hand_worked_year_matches_for_every_cadence() -> None:
    result = plan()
    assert [o.key for o in result.options] == ["monthly", "quarterly", "termly", "upfront"]
    expected = {
        "monthly": (12, "prov_a", 6_840_000),
        "quarterly": (4, "prov_a", 4_840_000),
        "termly": (2, "prov_b", 3_780_000),
        "upfront": (1, "prov_b", 2_850_000),
    }
    for key, (transfers, provider, total_cost) in expected.items():
        chosen = option(result, key)
        assert (chosen.transfers, chosen.provider_id, chosen.total_cost_bdt_minor) == (
            transfers,
            provider,
            total_cost,
        ), key


def test_savings_are_measured_against_sending_monthly() -> None:
    result = plan()
    assert option(result, "monthly").saving_vs_monthly_bdt_minor == 0
    assert option(result, "quarterly").saving_vs_monthly_bdt_minor == 6_840_000 - 4_840_000
    assert option(result, "upfront").saving_vs_monthly_bdt_minor == 6_840_000 - 2_850_000
    assert result.cheapest_key == "upfront"


def test_every_plan_delivers_exactly_the_total() -> None:
    for months in (1, 2, 5, 7, 12, 18):
        result = plan(total_minor=1_234_567, months=months)
        for chosen in result.options:
            assert sum(chosen.amounts_minor) == 1_234_567, (months, chosen.key)
            assert len(chosen.amounts_minor) == chosen.transfers


def test_a_provider_that_would_leave_the_university_short_loses_a_tie_on_cost() -> None:
    # Provider C is quoted as SHA and carries a shortfall: it must never beat a no-shortfall option.
    result = plan()
    for chosen in result.options:
        assert chosen.shortfall_foreign_minor == 0, chosen.key
        assert chosen.provider_id != "prov_c"


def test_cadences_that_collapse_to_the_same_number_of_transfers_are_listed_once() -> None:
    assert [o.key for o in plan(months=6).options] == ["monthly", "quarterly", "termly"]
    assert [o.key for o in plan(months=3).options] == ["monthly", "quarterly"]
    assert [o.key for o in plan(months=1).options] == ["monthly"]


def test_split_evenly_spreads_the_remainder_and_keeps_the_total() -> None:
    assert split_evenly(10, 3) == (4, 3, 3)
    assert split_evenly(9, 3) == (3, 3, 3)
    assert split_evenly(7, 1) == (7,)
    with pytest.raises(ValueError):
        split_evenly(5, 0)


def test_average_cost_percentage_is_a_decimal_and_lower_when_fees_are_shared() -> None:
    result = plan()
    assert isinstance(option(result, "monthly").avg_cost_pct, Decimal)
    assert option(result, "upfront").avg_cost_pct < option(result, "monthly").avg_cost_pct


def test_bad_inputs_are_refused() -> None:
    with pytest.raises(InvalidAmount):
        plan(total_minor=0)
    with pytest.raises(ValueError):
        plan(months=0)
    with pytest.raises(ValueError):
        plan(months=61)
