"""Currency-drop stress test: the same quote priced again if the taka weakens.

A what-if on synthetic rates. It uses the fee engine (no separate maths), keeps the same provider,
changes nothing and writes no audit event.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from tests.helpers import World


def stress(world: World, quote: dict[str, Any], query: str = "", who: str = "parent") -> Any:
    return world.call("GET", f"/quotes/{quote['quote_id']}/stress{query}", who)


def result_of(quote: dict[str, Any], provider_id: str) -> dict[str, Any]:
    return next(r for r in quote["results"] if r["provider_id"] == provider_id)


def test_the_baseline_is_the_quote_the_parent_already_has(world: World) -> None:
    quote = world.quote()
    body = stress(world, quote).json()
    chosen = result_of(quote, body["provider_id"])
    assert body["baseline"]["parent_pays_bdt_minor"] == chosen["parent_pays_bdt_minor"]
    assert body["baseline"]["mid_rate"] == quote["mid_rate"]["value"]
    assert body["target"] == quote["target"]
    assert body["synthetic"] is True and "not a forecast" in body["note"]
    assert "Indicative" in body["note"]


def test_a_weaker_taka_always_costs_more_and_more_for_a_bigger_drop(world: World) -> None:
    quote = world.quote()
    body = stress(world, quote).json()
    assert [s["drop_pct"] for s in body["scenarios"]] == ["5%", "10%", "15%", "20%"]
    extras = [s["extra_bdt_minor"] for s in body["scenarios"]]
    assert all(e > 0 for e in extras) and extras == sorted(extras)
    paid = [s["parent_pays_bdt_minor"] for s in body["scenarios"]]
    base = body["baseline"]["parent_pays_bdt_minor"]
    assert paid == [base + e for e in extras]


def test_only_the_rate_driven_part_moves_so_fixed_fees_in_taka_do_not(world: World) -> None:
    quote = world.quote()
    body = stress(world, quote, "?drops=10").json()
    chosen = result_of(quote, body["provider_id"])
    base = chosen["parent_pays_bdt_minor"]
    fixed = chosen["fees"]["fixed_bdt_minor"] + chosen["fees"]["swift_bdt_minor"]
    extra = body["scenarios"][0]["extra_bdt_minor"]
    tenth = Decimal("0.10")
    assert (base - fixed) * tenth - 5 <= extra <= base * tenth + 5
    assert extra < base * tenth  # the fixed fees did not grow with the rate


def test_custom_drops_are_sorted_and_deduplicated(world: World) -> None:
    body = stress(world, world.quote(), "?drops=25, 10,10").json()
    assert [s["drop_pct"] for s in body["scenarios"]] == ["10%", "25%"]


@pytest.mark.parametrize("query", ["?drops=0", "?drops=51", "?drops=1,2,3,4,5,6,7", "?drops=5,,x"])
def test_drops_outside_one_to_fifty_percent_are_refused(world: World, query: str) -> None:
    assert stress(world, world.quote(), query).status_code in {400, 422}


def test_the_provider_can_be_chosen_and_must_be_on_the_quote(world: World) -> None:
    quote = world.quote()
    body = stress(world, quote, "?provider_id=prov_c&drops=10").json()
    assert body["provider_id"] == "prov_c"
    assert stress(world, quote, "?provider_id=prov_zzz").status_code == 422


def test_by_default_it_stresses_the_provider_that_arrives_in_time(world: World) -> None:
    quote = world.quote(due_date="2026-10-15")
    assert stress(world, quote).json()["provider_id"] == "prov_a"
    cheapest = world.quote(due_date="2026-10-28")
    assert stress(world, cheapest).json()["provider_id"] == cheapest["results"][0]["provider_id"]


def test_the_student_may_read_it_and_it_writes_nothing(world: World) -> None:
    quote = world.quote()

    def changes() -> list[str]:
        return [r["action"] for r in world.audit_rows() if not r["action"].startswith("auth.")]

    before = changes()
    assert stress(world, quote, who="student").status_code == 200
    assert changes() == before
    assert world.call("GET", "/payments").json()["items"] == []


def test_nobody_else_and_nobody_signed_out_can_read_it(world: World) -> None:
    quote = world.quote()
    assert world.call("GET", f"/quotes/{quote['quote_id']}/stress", None).status_code == 401
    assert world.call("GET", "/quotes/qte_missing/stress").status_code == 404
