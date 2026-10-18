"""Rules configuration: YAML seeds the table, the typed view feeds the engine."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from app.core import errors
from app.core.clock import FakeClock
from app.core.db import Database
from app.domain import rules as rules_module
from app.domain.rules import (
    flatten_rules,
    load_rules,
    sync_rules_from_file,
    update_rule,
)
from app.engine.money import Money
from app.engine.quote import ChargeCode, MidRate, build_quote

RULES_FILE = Path(__file__).resolve().parents[2] / "config" / "rules.yaml"
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)


@pytest.fixture
def seeded(db: Database) -> Database:
    with db.write() as session:
        sync_rules_from_file(session, RULES_FILE, NOW)
    return db


def test_yaml_flattens_into_dotted_rule_keys() -> None:
    flat = flatten_rules(RULES_FILE)
    assert "engine.quote_ttl_seconds" in flat
    assert "providers.prov_b" in flat
    assert "calendars.weekend.BD" in flat
    assert flat["limits.daily_usd_equivalent"]["value"] == 100000
    assert "schema_version" not in flat


def test_every_regulatory_rule_is_unverified_or_has_a_source() -> None:
    for key, rule in flatten_rules(RULES_FILE).items():
        if rule.get("kind") == "regulatory" and rule.get("verified"):
            assert rule.get("source_url"), key


def test_living_expense_figures_stay_unverified_because_the_circular_does_not_state_them() -> None:
    flat = flatten_rules(RULES_FILE)
    for key in (
        "bangladesh_rules.living_expense_usd_per_month",
        "bangladesh_rules.living_expense_high_cost_uplift_pct",
    ):
        assert flat[key]["verified"] is False
        assert flat[key]["source_url"]
        assert "NOT in the official text" in flat[key]["note"]


def test_bangladesh_rules_marked_verified_point_at_the_official_circular() -> None:
    flat = flatten_rules(RULES_FILE)
    official = "https://www.bb.org.bd/mediaroom/circulars/fepd/sep302026fepd-140e.pdf"
    verified = {
        key: rule
        for key, rule in flat.items()
        if key.startswith("bangladesh_rules.") and rule.get("verified")
    }
    assert {
        "bangladesh_rules.single_ad_branch_rule",
        "bangladesh_rules.release_period_limit",
        "bangladesh_rules.release_basis",
        "bangladesh_rules.international_card_for_education",
    } <= set(verified)
    for key, rule in verified.items():
        assert rule["source_url"] == official, key
        assert rule["last_checked"] == "2026-10-18", key
        assert "onfirm with your AD bank" in rule["note"], key


def test_sync_inserts_once_and_never_overwrites_admin_edits(seeded: Database) -> None:
    clock = FakeClock(NOW)
    with seeded.write() as session:
        update_rule(
            session,
            key="limits.daily_usd_equivalent",
            value=120000,
            source_url=None,
            verified=True,
            reason="raise for the demo",
            updated_by="usr_admin",
            now=clock.now(),
        )
    with seeded.write() as session:
        assert sync_rules_from_file(session, RULES_FILE, NOW) == 0
    with seeded.read() as session:
        assert load_rules(session).daily_limit_usd == 120000


def test_typed_view_reproduces_the_worked_example_from_config(seeded: Database) -> None:
    with seeded.read() as session:
        rules = load_rules(session)
    quote = build_quote(
        target=Money(1_000_000, "GBP"),
        purpose="TUITION",
        destination_country="GB",
        charge_code=ChargeCode.OUR,
        mid_rate=MidRate(rules.mid_rate("GBP"), "synthetic", NOW),
        providers=rules.provider_terms(),
        params=rules.engine_params(),
        now=NOW,
    )
    assert [r.provider_id for r in quote.results] == ["prov_b", "prov_c", "prov_a"]
    assert [r.cost_pct_display for r in quote.results] == ["1.58", "1.63", "2.16"]


def test_typed_view_exposes_calendars_planner_and_limits(seeded: Database) -> None:
    with seeded.read() as session:
        rules = load_rules(session)
    bd, gb = rules.calendars("GB")
    assert bd.country == "BD"
    assert bd.weekend == frozenset({4, 5})
    assert gb.holidays[date(2026, 12, 28)].startswith("Boxing Day")
    params = rules.planner_params()
    assert params.settlement_business_days == 3
    assert params.buffer_days == 2
    assert params.cutoff == time(15, 0)
    assert rules.per_transaction_limit_usd == 50000
    assert rules.quote_ttl_seconds == 300
    assert rules.mfa_proof_ttl_seconds == 300


def test_corridors_and_checklists(seeded: Database) -> None:
    with seeded.read() as session:
        rules = load_rules(session)
    assert rules.corridor("GB").currency == "GBP"
    featured = {code for code, c in rules.corridors().items() if c.featured}
    assert featured == {"GB", "US", "DE", "AU", "CA", "MY"}
    checklist = rules.checklist("GB", "TUITION")
    keys = [item["key"] for item in checklist["items"]]
    assert keys[:3] == ["offer_letter", "fee_demand_note", "passport"]
    assert checklist["verified"] is False
    assert checklist["indicative"] == "Indicative. Confirm with your AD bank."
    with pytest.raises(errors.ValidationFailed):
        rules.checklist("ZZ", "TUITION")


def test_api_view_marks_unverified_rules_with_the_badge(seeded: Database) -> None:
    with seeded.read() as session:
        by_key = {r["key"]: r for r in load_rules(session).to_api()}
    unverified = by_key["bangladesh_rules.living_expense_usd_per_month"]
    assert unverified["badge"] == "NOT_VERIFIED"
    assert unverified["indicative"] == "Indicative. Confirm with your AD bank."
    assert by_key["engine.quote_ttl_seconds"]["badge"] is None


def test_update_rule_validates_type_and_range(seeded: Database) -> None:
    def attempt(key: str, value: object) -> None:
        with seeded.write() as session:
            update_rule(
                session,
                key=key,
                value=value,
                source_url=None,
                verified=False,
                reason="test",
                updated_by="usr_admin",
                now=NOW,
            )

    for key, bad in [
        ("engine.quote_ttl_seconds", "soon"),
        ("engine.quote_ttl_seconds", 5),
        ("limits.daily_usd_equivalent", -1),
        ("calendars.weekend.BD", ["Funday"]),
        ("fx.mid_rates.GBP", "0"),
        ("no.such.rule", 1),
    ]:
        with pytest.raises(errors.ValidationFailed):
            attempt(key, bad)
    attempt("engine.quote_ttl_seconds", 600)


def test_rules_module_has_no_hard_coded_regulatory_numbers() -> None:
    source = Path(rules_module.__file__).read_text(encoding="utf-8")
    assert "50000" not in source
    assert "2000" not in source
