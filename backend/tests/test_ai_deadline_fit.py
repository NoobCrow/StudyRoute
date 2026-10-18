"""The assistant proposes the cheapest provider that ARRIVES before the due date.

The fake clock starts on Wednesday 14 October 2026. The synthetic providers settle in 1 (A), 2 (B)
and 3 (C) business days, counting only days that both Bangladesh and the UK work. B is the cheapest
overall, so a very tight deadline makes the assistant pass over it, and say why.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import World


def plan(world: World, due: str) -> dict[str, Any]:
    message = f"I need to pay GBP 10,000 tuition by {due}"
    response = world.call("POST", "/assistant/chat", json={"message": message, "context": {}})
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_a_comfortable_deadline_proposes_the_cheapest_and_says_it_arrives_in_time(
    world: World,
) -> None:
    reply = plan(world, "28 October")
    card = reply["task"]
    assert card["best"]["provider_id"] == "prov_b" and card["best"]["meets_deadline"] is True
    assert card["cheapest_misses_deadline"] is False
    assert "in time" in reply["reply"]
    assert reply["guard"]["status"] == "passed"


def test_a_tight_deadline_passes_over_the_cheapest_and_proposes_one_that_arrives(
    world: World,
) -> None:
    reply = plan(world, "15 October")
    card = reply["task"]
    assert card["cheapest_misses_deadline"] is True
    assert card["best"]["provider_id"] == "prov_a"
    assert card["best"]["arrives_on"] == "2026-10-15" and card["best"]["meets_deadline"] is True
    assert card["draft"]["provider_id"] == "prov_a"
    skipped = next(a for a in card["alternatives"] if a["provider_id"] == "prov_b")
    assert skipped["meets_deadline"] is False
    text = reply["reply"]
    assert "after your due date" in text and "cheapest provider that arrives in time" in text
    assert "Provider A" in text and "Provider B" in text
    assert reply["guard"]["status"] == "passed"


def test_when_nobody_arrives_in_time_it_says_so_and_proposes_the_fastest(world: World) -> None:
    reply = plan(world, "14 October")
    card = reply["task"]
    assert card["best"]["provider_id"] == "prov_a"
    assert "No provider can arrive by" in reply["reply"]
    assert "Ask the university whether it can wait" in reply["reply"]
    assert card["best"]["meets_deadline"] is False


def test_the_proposal_is_still_only_a_proposal_and_creates_no_payment(world: World) -> None:
    plan(world, "15 October")
    assert world.call("GET", "/payments").json()["items"] == []
    assert world.audit_rows(action="payment.created") == []


def test_without_a_due_date_nothing_about_the_plan_changes(world: World) -> None:
    response = world.call(
        "POST",
        "/assistant/chat",
        json={"message": "I need to pay GBP 10,000 tuition", "context": {}},
    )
    body = response.json()
    if body["task"]["status"] == "ready":
        assert body["task"]["deadline_fit"] is None
        assert body["task"]["best"]["provider_id"] == "prov_b"
