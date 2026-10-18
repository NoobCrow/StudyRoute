"""Fee engine. T01 reproduces the blueprint 6.3 worked example exactly."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.engine.money import InvalidAmount, Money
from app.engine.quote import (
    ChargeCode,
    EngineParams,
    MidRate,
    ProviderTerms,
    build_quote,
    compute_provider_result,
)

NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
MID = MidRate(Decimal("160.000000"), "synthetic", NOW - timedelta(seconds=10))
ALL_CODES = (ChargeCode.OUR, ChargeCode.SHA, ChargeCode.BEN)


def synthetic_providers() -> list[ProviderTerms]:
    return [
        ProviderTerms(
            provider_id="prov_a",
            name="Provider A (synthetic)",
            margin_pct=Decimal("2.00"),
            fixed_fee_bdt_minor=150_000,
            swift_fee_bdt_minor=100_000,
            intermediary_fee_major=Decimal("0"),
            receiving_fee_major=Decimal("0"),
            supported_charge_codes=ALL_CODES,
            default_charge_code=ChargeCode.OUR,
            eta_business_days=1,
        ),
        ProviderTerms(
            provider_id="prov_b",
            name="Provider B (synthetic)",
            margin_pct=Decimal("1.00"),
            fixed_fee_bdt_minor=300_000,
            swift_fee_bdt_minor=150_000,
            intermediary_fee_major=Decimal("30"),
            receiving_fee_major=Decimal("0"),
            supported_charge_codes=ALL_CODES,
            default_charge_code=ChargeCode.OUR,
            eta_business_days=2,
        ),
        ProviderTerms(
            provider_id="prov_c",
            name="Provider C (synthetic)",
            margin_pct=Decimal("1.25"),
            fixed_fee_bdt_minor=50_000,
            swift_fee_bdt_minor=0,
            intermediary_fee_major=Decimal("25"),
            receiving_fee_major=Decimal("10"),
            supported_charge_codes=(ChargeCode.SHA,),
            default_charge_code=ChargeCode.SHA,
            eta_business_days=3,
        ),
    ]


def quote_for(target_minor: int = 1_000_000, charge: ChargeCode = ChargeCode.OUR):
    return build_quote(
        target=Money(target_minor, "GBP"),
        purpose="TUITION",
        destination_country="GB",
        charge_code=charge,
        mid_rate=MID,
        providers=synthetic_providers(),
        params=EngineParams(),
        now=NOW,
    )


def test_T01_worked_example_ranks_b_c_a_with_exact_percentages() -> None:
    quote = quote_for()
    assert [r.provider_id for r in quote.results] == ["prov_b", "prov_c", "prov_a"]
    assert [r.rank for r in quote.results] == [1, 2, 3]
    pct = {r.provider_id: r.cost_pct_display for r in quote.results}
    assert pct == {"prov_b": "1.58", "prov_c": "1.63", "prov_a": "2.16"}


def test_T01_provider_b_numbers_match_blueprint_check() -> None:
    b = quote_for().results[0]
    assert b.provider_rate == Decimal("161.600000")
    assert b.margin_pct_display == "1.00"
    assert b.charge_code is ChargeCode.OUR
    assert b.fx_cost_bdt_minor == 1_600_000
    assert b.sender_extra_bdt_minor == 480_000
    assert b.total_cost_bdt_minor == 2_530_000
    assert b.parent_pays_bdt_minor == 162_530_000
    assert b.shortfall_foreign_minor == 0
    assert b.intermediary_foreign_minor == 3000
    assert b.warnings == ()


def test_T01_provider_c_shortfall_is_flagged() -> None:
    c = quote_for().results[1]
    assert c.provider_id == "prov_c"
    assert c.charge_code is ChargeCode.SHA
    assert c.shortfall_foreign_minor == 3500
    assert c.shortfall_bdt_minor == 560_000
    assert c.total_cost_bdt_minor == 2_610_000
    assert c.parent_pays_bdt_minor == 162_050_000
    codes = {w.code for w in c.warnings}
    assert codes == {"SHORTFALL_RISK", "CHARGE_CODE_FALLBACK"}


def test_T01_provider_a_numbers() -> None:
    a = quote_for().results[2]
    assert a.total_cost_bdt_minor == 3_450_000
    assert a.parent_pays_bdt_minor == 163_450_000
    assert a.shortfall_foreign_minor == 0


def test_total_cost_is_the_exact_sum_of_its_parts() -> None:
    for result in quote_for().results:
        parts = (
            result.fx_cost_bdt_minor
            + result.fixed_fee_paid_by_sender_bdt_minor
            + result.swift_fee_bdt_minor
            + result.sender_extra_bdt_minor
            + result.shortfall_bdt_minor
        )
        assert parts == result.total_cost_bdt_minor


def test_sha_request_moves_intermediary_fee_from_sender_to_beneficiary() -> None:
    quote = quote_for(charge=ChargeCode.SHA)
    b = next(r for r in quote.results if r.provider_id == "prov_b")
    assert b.charge_code is ChargeCode.SHA
    assert b.sender_extra_bdt_minor == 0
    assert b.shortfall_foreign_minor == 3000
    assert b.total_cost_bdt_minor == 1_600_000 + 300_000 + 150_000 + 480_000
    assert b.parent_pays_bdt_minor == 161_600_000 + 300_000 + 150_000


def test_ben_also_deducts_the_provider_fixed_fee_from_the_beneficiary() -> None:
    terms = synthetic_providers()[1]
    result = compute_provider_result(
        target=Money(1_000_000, "GBP"),
        mid_rate=MID.value,
        terms=terms,
        requested_charge_code=ChargeCode.BEN,
        params=EngineParams(ben_deducts_fixed_fee=True),
    )
    assert result.fixed_fee_paid_by_sender_bdt_minor == 0
    assert result.shortfall_foreign_minor == 3000 + 1875
    assert result.parent_pays_bdt_minor == 161_600_000 + 150_000


def test_ben_config_flag_can_keep_the_fixed_fee_with_the_sender() -> None:
    result = compute_provider_result(
        target=Money(1_000_000, "GBP"),
        mid_rate=MID.value,
        terms=synthetic_providers()[1],
        requested_charge_code=ChargeCode.BEN,
        params=EngineParams(ben_deducts_fixed_fee=False),
    )
    assert result.fixed_fee_paid_by_sender_bdt_minor == 300_000
    assert result.shortfall_foreign_minor == 3000


def test_quote_has_expiry_and_stable_input_hash() -> None:
    first, second = quote_for(), quote_for()
    assert first.expires_at == NOW + timedelta(seconds=300)
    assert first.created_at == NOW
    assert first.input_hash == second.input_hash
    assert first.input_hash.startswith("sha256:")
    assert quote_for(target_minor=1_000_001).input_hash != first.input_hash


def test_ttl_comes_from_params() -> None:
    quote = build_quote(
        target=Money(1_000_000, "GBP"),
        purpose="TUITION",
        destination_country="GB",
        charge_code=ChargeCode.OUR,
        mid_rate=MID,
        providers=synthetic_providers(),
        params=EngineParams(quote_ttl_seconds=900),
        now=NOW,
    )
    assert quote.expires_at == NOW + timedelta(seconds=900)


def test_non_positive_target_is_rejected_by_the_engine() -> None:
    for bad in (0, -100):
        with pytest.raises(InvalidAmount):
            quote_for(target_minor=bad)


def test_ranking_is_deterministic_on_ties() -> None:
    twin = synthetic_providers()[1]
    clone = ProviderTerms(**{**twin.__dict__, "provider_id": "prov_a2", "name": "Twin"})
    quote = build_quote(
        target=Money(1_000_000, "GBP"),
        purpose="TUITION",
        destination_country="GB",
        charge_code=ChargeCode.OUR,
        mid_rate=MID,
        providers=[clone, twin],
        params=EngineParams(),
        now=NOW,
    )
    assert [r.provider_id for r in quote.results] == ["prov_a2", "prov_b"]


def test_rates_keep_six_decimal_places() -> None:
    mid = MidRate(Decimal("122.123457"), "synthetic", NOW)
    result = compute_provider_result(
        target=Money(500_000, "USD"),
        mid_rate=mid.value,
        terms=synthetic_providers()[0],
        requested_charge_code=ChargeCode.OUR,
        params=EngineParams(),
    )
    assert result.provider_rate == Decimal("124.565926")


def test_api_dict_contains_blueprint_fields() -> None:
    body = quote_for().results[0].to_api_dict()
    for key in (
        "rank",
        "provider_id",
        "provider_name",
        "provider_rate",
        "margin_pct",
        "charge_code",
        "fees",
        "shortfall_foreign_minor",
        "total_cost_bdt_minor",
        "cost_pct",
        "parent_pays_bdt_minor",
        "eta_business_days",
        "warnings",
        "display",
    ):
        assert key in body
    assert body["fees"] == {
        "fixed_bdt_minor": 300_000,
        "swift_bdt_minor": 150_000,
        "intermediary_foreign_minor": 3000,
        "receiving_foreign_minor": 0,
    }
    assert body["display"]["total_cost"] == "BDT 25,300.00"
    assert body["display"]["parent_pays"] == "BDT 1,625,300.00"
