"""The bank network configuration and how the seed script adds it to an existing database."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.domain.bank_directory import load_directory, parse_directory
from app.scripts.seed import ensure_bank_network
from tests.helpers import World

CONFIG = Path(__file__).resolve().parents[2] / "config" / "bank_network.yaml"


def raw() -> dict[str, Any]:
    return dict(yaml.safe_load(CONFIG.read_text(encoding="utf-8")))


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    instance = World(tmp_path)  # seeded without the bank network, like a database that predates it
    yield instance
    instance.close()


def test_the_shipped_config_loads_and_every_bank_is_synthetic() -> None:
    directory = load_directory(CONFIG)
    assert all(code.startswith("EXMP") for code in directory.banks)
    assert directory.correspondent.code == "EXMPUS6C"
    assert directory.host_currencies() == ["AUD", "CAD", "EUR", "GBP", "MYR", "USD"]
    assert {b.provider_id for b in directory.with_role("AD_BANK")} == {"prov_a", "prov_b", "prov_c"}
    assert all("(synthetic)" in a.holder for a in directory.demo_accounts)


def test_every_demo_account_number_is_unique_and_the_gb_ones_match_the_seeded_recipients() -> None:
    directory = load_directory(CONFIG)
    numbers = [a.number for a in directory.demo_accounts]
    assert len(numbers) == len(set(numbers))
    assert "GB08EXMP12345612344821" in numbers and "GB13EXMP12345600005555" in numbers


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d["demo_accounts"][0].update(bank="NOPE"), "unknown bank"),
        (lambda d: d["demo_accounts"][0].update(currency="USD"), "does not match"),
        (
            lambda d: d["demo_accounts"][1].update(number=d["demo_accounts"][0]["number"]),
            "duplicate",
        ),
        (lambda d: d["demo_accounts"][0].update(owner="stranger"), "owner must be"),
        (lambda d: d["banks"].pop("EXMPUS6C"), "CORRESPONDENT"),
        (lambda d: d["banks"]["EXMPBDA1"].update(currency="GBP"), "AD bank"),
        (lambda d: d["timing"].update(international_delays=[1, 2]), "three numbers"),
        (lambda d: d["clearing_houses"].pop("CLR-GB"), "no clearing house"),
    ],
)
def test_a_broken_config_is_refused_at_load_time(mutate: Any, message: str) -> None:
    data = copy.deepcopy(raw())
    mutate(data)
    with pytest.raises(ValueError, match=message):
        parse_directory(data)


def test_the_seed_adds_the_network_to_a_database_that_predates_it(world: World) -> None:
    with world.ctx.db.read() as session:
        assert not world.ctx.bank.is_ready(session)
    created = ensure_bank_network(world.ctx)
    assert created > 100
    with world.ctx.db.read() as session:
        assert world.ctx.bank.is_ready(session)
        assert world.ctx.bank.network_overview(session)["all_ok"]


def test_running_the_seed_again_changes_nothing_and_writes_no_second_event(world: World) -> None:
    ensure_bank_network(world.ctx)
    assert ensure_bank_network(world.ctx) == 0
    rows = world.call("GET", "/audit/events?limit=100", "admin").json()["items"]
    assert [r["action"] for r in rows].count("system.bank_network_ready") == 1


def test_the_household_accounts_wait_for_the_demo_users(tmp_path: Path) -> None:
    from app.container import build_context
    from tests.helpers import make_settings

    ctx = build_context(make_settings(tmp_path))
    try:
        with ctx.db.write() as session:
            first = ctx.bank.ensure_network(session)
        with ctx.db.read() as session:
            assert not ctx.bank.is_ready(session)  # the first demo account is a parent's
        assert first > 0
    finally:
        ctx.db.dispose()
