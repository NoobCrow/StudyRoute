"""GET /planner/send-plan: the smart send plan over the API."""

from __future__ import annotations

from typing import Any

from tests.helpers import World

QUERY = "monthly_minor=100000&months=12&currency=GBP"


def get_plan(world: World, query: str = QUERY, who: str | None = "parent") -> Any:
    return world.call("GET", f"/planner/send-plan?{query}", who)


def test_a_parent_gets_the_four_cadences_with_the_engine_numbers(world: World) -> None:
    response = get_plan(world)
    assert response.status_code == 200
    body = response.json()
    assert body["total"]["formatted"] == "GBP 12,000.00"
    assert [o["key"] for o in body["options"]] == ["monthly", "quarterly", "termly", "upfront"]
    monthly = body["options"][0]
    assert monthly["transfers"] == 12 and monthly["provider_id"] == "prov_a"
    assert monthly["total_cost_bdt_minor"] == 6_840_000
    assert monthly["display"]["total_cost"] == "BDT 68,400.00"
    assert body["cheapest_key"] == "upfront"
    upfront = body["options"][3]
    assert upfront["display"]["saving_vs_monthly"] == "BDT 39,900.00"


def test_the_plan_is_labelled_synthetic_and_never_claims_to_forecast(world: World) -> None:
    body = get_plan(world).json()
    assert body["synthetic"] is True
    assert "Indicative. Confirm with your AD bank." in body["disclaimer"]
    assert "does not predict" in body["trade_off"]


def test_a_transfer_above_the_sandbox_cap_is_flagged_not_hidden(world: World) -> None:
    body = get_plan(world, "monthly_minor=100000000&months=1&currency=GBP").json()
    assert body["options"][0]["exceeds_sandbox_cap"] is True
    assert get_plan(world).json()["options"][0]["exceeds_sandbox_cap"] is False


def test_students_may_plan_but_the_reviewer_may_not(world: World) -> None:
    assert get_plan(world, who="student").status_code == 200
    assert get_plan(world, who="admin").status_code == 403
    assert get_plan(world, who=None).status_code == 401


def test_bad_inputs_are_validation_failures(world: World) -> None:
    for query in (
        "monthly_minor=0&months=12&currency=GBP",
        "monthly_minor=100000&months=0&currency=GBP",
        "monthly_minor=100000&months=61&currency=GBP",
        "monthly_minor=100000&months=12&currency=XXX",
        "monthly_minor=100000&months=12&currency=GBP&charge_code=FREE",
        "months=12&currency=GBP",
    ):
        response = get_plan(world, query)
        assert response.status_code == 422, query
        assert response.json()["code"] == "VALIDATION_FAILED", query


def test_a_sha_request_is_priced_with_the_provider_that_does_not_leave_the_university_short(
    world: World,
) -> None:
    body = get_plan(world, QUERY + "&charge_code=SHA").json()
    for option in body["options"]:
        assert option["shortfall_foreign_minor"] == 0
        assert option["provider_id"] == "prov_a"
