"""Every country is a destination: generated defaults sit under the six hand-written corridors.

The hand-written rules (GB, US, DE, AU, CA, MY) must win. Everything else comes from the
`countries` section of config/rules.yaml, which scripts/gen_countries.py writes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.ai.request_parser import parse_request
from app.core import errors
from app.core.db import Database
from app.domain.rules import Rules, load_rules, sync_rules_from_file
from app.engine import fx
from app.engine.money import CURRENCY_EXPONENTS, Money
from app.engine.quote import ChargeCode, MidRate, build_quote
from tests.helpers import World

RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "rules.yaml"
NOW = datetime(2026, 10, 15, 5, 0, tzinfo=UTC)
FEATURED = ["AU", "CA", "DE", "GB", "MY", "US"]
RESTRICTED = {"CU", "IR", "KP", "SY"}


@pytest.fixture
def rules(db: Database) -> Rules:
    with db.write() as session:
        sync_rules_from_file(session, RULES_FILE, NOW)
    with db.read() as session:
        return load_rules(session)


def test_every_country_is_listed_once_and_the_featured_six_come_first(rules: Rules) -> None:
    corridors = rules.corridors()
    assert len(corridors) >= 190
    assert list(corridors)[:6] == FEATURED
    assert [c for c, v in corridors.items() if v.featured] == FEATURED
    assert "BD" not in corridors, "Bangladesh is where the money starts, not a destination"
    names = [c.name for c in corridors.values()]
    assert len(set(names)) == len(names)
    generated = [c.name for c in corridors.values() if not c.featured]
    assert generated == sorted(generated), "the rest are listed by name"


@pytest.mark.parametrize(
    ("code", "name", "currency"),
    [
        ("JP", "Japan", "JPY"), ("IN", "India", "INR"), ("CN", "China", "CNY"),
        ("NO", "Norway", "NOK"), ("NA", "Namibia", "NAD"), ("KR", "South Korea", "KRW"),
        ("AE", "United Arab Emirates", "AED"), ("HK", "Hong Kong", "HKD"),
        ("TW", "Taiwan", "TWD"), ("XK", "Kosovo", "EUR"), ("VA", "Vatican City", "EUR"),
        ("KW", "Kuwait", "KWD"), ("NZ", "New Zealand", "NZD"), ("TR", "Türkiye", "TRY"),
    ],
)  # fmt: skip
def test_known_countries_have_the_right_name_and_currency(
    rules: Rules, code: str, name: str, currency: str
) -> None:
    corridor = rules.corridor(code)
    assert (corridor.name, corridor.currency, corridor.featured) == (name, currency, False)


def test_the_hand_written_corridors_are_not_overridden_by_the_generated_ones(rules: Rules) -> None:
    gb = rules.corridor("GB")
    assert gb.featured and gb.account_scheme == "IBAN_OR_UK_DOMESTIC"
    assert gb.host_rail == "UK Faster Payments or CHAPS"
    assert rules.mid_rate("GBP") == Decimal("160.000000")
    assert rules.calendar("GB").holidays, "the UK keeps its own bank holidays"
    assert rules.checklist("GB", "TUITION")["items"][-1]["key"] == "cas_number"


def test_every_country_has_what_the_app_needs(rules: Rules) -> None:
    for code, corridor in rules.corridors().items():
        assert corridor.currency in CURRENCY_EXPONENTS, code
        assert rules.mid_rate(corridor.currency) > 0, code
        assert 1 <= len(rules.calendar(code).weekend) <= 3, code
        for purpose in ("TUITION", "LIVING"):
            checklist = rules.checklist(code, purpose)
            assert checklist["items"], (code, purpose)
            assert checklist["indicative"] == "Indicative. Confirm with your AD bank."
        assert corridor.account_scheme in {"IBAN", "IBAN_OR_UK_DOMESTIC", "ABA_ACCOUNT", "ACCOUNT"}


def test_account_scheme_follows_the_iban_registry(rules: Rules) -> None:
    assert rules.corridor("FR").account_scheme == "IBAN"
    assert rules.corridor("SA").account_scheme == "IBAN"
    assert rules.corridor("JP").account_scheme == "ACCOUNT"
    assert rules.corridor("IN").account_scheme == "ACCOUNT"


def test_generated_countries_use_a_general_checklist_and_say_so(rules: Rules) -> None:
    jp = rules.checklist("JP", "TUITION")
    assert "Japan are not loaded" in jp["note"]
    assert jp["verified"] is False
    assert [i["key"] for i in jp["items"]] == [
        "offer_letter", "fee_demand_note", "passport", "visa", "parent_id", "source_of_funds",
        "ad_bank_form", "receiving_account_details",
    ]  # fmt: skip
    assert "not loaded" not in rules.checklist("GB", "TUITION")["note"]
    with pytest.raises(errors.ValidationFailed):
        rules.checklist("ZZ", "TUITION")


def test_weekends_come_from_the_directory_and_unknown_countries_fail(rules: Rules) -> None:
    friday, saturday = 4, 5
    assert rules.calendar("SA").weekend == frozenset({friday, saturday})
    assert rules.calendar("JP").weekend == frozenset({saturday, 6})
    assert rules.calendar("JP").holidays == {}
    with pytest.raises(errors.ValidationFailed):
        rules.calendar("ZZ")


def test_restricted_destinations_are_listed_but_never_quoted_or_saved(rules: Rules) -> None:
    assert {c for c, v in rules.corridors().items() if v.restricted} == RESTRICTED
    assert rules.corridor("KP").restricted
    for code in RESTRICTED:
        with pytest.raises(errors.ValidationFailed, match="does not quote payments"):
            rules.open_corridor(code)
    assert rules.open_corridor("JP").name == "Japan"


def test_every_country_quotes_through_the_fee_engine(rules: Rules) -> None:
    """All currencies work end to end: money in minor units, no float, sane totals."""
    providers = rules.provider_terms()
    for code, corridor in rules.corridors().items():
        mid = rules.mid_rate(corridor.currency)
        sample = fx.sample_amount_major(mid)
        quote = build_quote(
            target=Money.from_major(sample, corridor.currency),
            purpose="TUITION",
            destination_country=code,
            charge_code=ChargeCode.OUR,
            mid_rate=MidRate(mid, "synthetic", NOW),
            providers=providers,
            params=rules.engine_params(),
            now=NOW,
        )
        assert len(quote.results) == 3, code
        for result in quote.results:
            assert result.parent_pays_bdt_minor > 0, code
            assert result.total_cost_bdt_minor > 0, code
            assert isinstance(result.parent_pays_bdt_minor, int), code
        # The cheapest provider on a BDT 1.6 million tuition payment costs well under 10%.
        assert min(r.cost_pct for r in quote.results) < Decimal(10), (
            code,
            quote.results[0].cost_pct,
        )


def test_sample_amounts_are_round_and_worth_about_bdt_1_6_million() -> None:
    assert fx.sample_amount_major(Decimal("160")) == 10_000
    assert fx.sample_amount_major(Decimal("0.813333")) == 2_000_000
    assert fx.sample_amount_major(Decimal("397.394")) == 4_000
    for rate in ("0.002905", "0.0049", "1", "26", "122", "397", "1500"):
        sample = fx.sample_amount_major(Decimal(rate))
        worth = Decimal(sample) * Decimal(rate)
        assert Decimal(1_000_000) <= worth <= Decimal(2_400_000), (rate, sample)
        assert str(sample).rstrip("0") in "123456789", "one significant figure"


def test_currency_exponents_match_iso_for_the_odd_ones() -> None:
    assert CURRENCY_EXPONENTS["JPY"] == 0
    assert CURRENCY_EXPONENTS["KRW"] == 0
    assert CURRENCY_EXPONENTS["KWD"] == 3
    assert CURRENCY_EXPONENTS["BHD"] == 3
    assert CURRENCY_EXPONENTS["USD"] == CURRENCY_EXPONENTS["GBP"] == 2
    assert Money.from_major("1000", "KWD").amount_minor == 1_000_000
    assert Money.from_major("1000", "JPY").amount_minor == 1000


def test_quote_and_recipient_apis_refuse_a_restricted_destination(world: World) -> None:
    body = {
        "target": {"amount_minor": 1_000_000, "currency": "KPW"},
        "purpose": "TUITION", "destination_country": "KP", "charge_code": "OUR",
    }  # fmt: skip
    refused = world.call("POST", "/quotes", "parent", json=body)
    assert refused.status_code in {400, 422}
    assert "does not quote payments to North Korea" in refused.text


def test_a_quote_for_a_generated_country_works_through_the_api(world: World) -> None:
    quote = world.quote(
        target={"amount_minor": 2_000_000, "currency": "JPY"},
        destination_country="JP",
        due_date="2026-10-28",
    )
    assert quote["target"]["currency"] == "JPY"
    assert len(quote["results"]) == 3
    assert quote["results"][0]["rank"] == 1


def test_the_planner_and_checklist_endpoints_accept_any_country(world: World) -> None:
    checklist = world.call("GET", "/checklist?country=NG&purpose=TUITION", "parent")
    assert checklist.status_code == 200, checklist.text
    assert "Nigeria are not loaded" in checklist.json()["note"]
    planner = world.call("GET", "/planner/deadline?country=NG&due_date=2026-12-01", "parent")
    assert planner.status_code == 200, planner.text


@pytest.mark.parametrize(
    "message",
    [
        "I need to pay JPY 2,000,000 tuition by 28 October",
        "send 2,000,000 jpy for fees by 28 October",
    ],
)
def test_the_assistant_reads_amounts_in_the_new_currencies(rules: Rules, message: str) -> None:
    got = parse_request(message, rules.supported_currencies(), date(2026, 10, 15))
    assert (got.currency, got.amount_minor) == ("JPY", 2_000_000)


@pytest.mark.parametrize(
    "message",
    [
        "Show me the top 5 universities in the UK",
        "I will try 500 pounds first",
        "all 200 students need to pay",
        "a pen 20 pack",
    ],
)
def test_english_words_that_are_currency_codes_are_not_read_as_money(
    rules: Rules, message: str
) -> None:
    got = parse_request(message, rules.supported_currencies(), date(2026, 10, 15))
    assert got.currency in (None, "GBP"), (message, got.currency)
    assert got.currency != "TOP" and got.currency != "TRY"


def test_uppercase_codes_that_look_like_words_still_work(rules: Rules) -> None:
    got = parse_request(
        "pay TRY 50,000 by 28 October", rules.supported_currencies(), date(2026, 10, 15)
    )
    assert (got.currency, got.amount_minor) == ("TRY", 5_000_000)
