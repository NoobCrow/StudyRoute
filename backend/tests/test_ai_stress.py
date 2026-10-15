"""The assistant answers "what if the taka drops?" from the engine's stress test.

It is a question (a what-if on a quote that is already open), not a task: it creates nothing, every
figure comes from the fee engine, and the number guard checks the answer like any other.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.ai.intents import Intent, choose_intent, stress_drops
from app.ai.nlu.runtime import load_reader
from app.ai.number_guard import numbers_in
from app.ai.request_parser import parse_request
from tests.helpers import World

TODAY = date(2026, 10, 14)


def intent_of(message: str, *, has_context: bool = False) -> Intent:
    parsed = parse_request(message, ["GBP", "USD", "EUR"], TODAY)
    return choose_intent(message, parsed, has_context=has_context)


@pytest.mark.parametrize(
    "message",
    [
        "What if the taka drops 10%?",
        "Run a stress test on this quote",
        "stress-test the payment please",
        "How bad is a currency drop for me?",
        "what if the pound goes up by 15 percent",
        "If the taka weakens, how much more do I pay?",
        "What happens if the BDT depreciates?",
        "what if the taka drops 10% on my GBP 10,000 tuition",
    ],
)
def test_a_what_if_about_the_rate_is_a_stress_question(message: str) -> None:
    assert intent_of(message) is Intent.STRESS
    assert intent_of(message, has_context=True) is Intent.STRESS


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Why is Provider B cheaper than A?", Intent.COMPARE),
        ("What is the exchange rate today?", Intent.COMPARE),
        ("I need to pay GBP 10,000 tuition by 28 October", Intent.PLAN),
        ("What if I pay late?", Intent.HELP),
        ("I am stressed about the fees", Intent.COMPARE),
    ],
)
def test_other_questions_are_not_taken_for_a_stress_test(message: str, expected: Intent) -> None:
    assert intent_of(message) is expected


def test_named_percentages_are_added_to_the_usual_four_and_capped() -> None:
    assert stress_drops("hello") == (Decimal(5), Decimal(10), Decimal(15), Decimal(20))
    assert stress_drops("what if the taka drops 12%") == tuple(
        Decimal(n) for n in (5, 10, 12, 15, 20)
    )
    assert Decimal(70) not in stress_drops("what if the taka drops 70%")
    many = stress_drops("what if the taka drops 1%, 2%, 3%, 4% or 30%")
    assert len(many) <= 6 and Decimal(30) in many and Decimal(1) in many


def ask(world: World, message: str, **context: Any) -> dict[str, Any]:
    response = world.call("POST", "/assistant/chat", json={"message": message, "context": context})
    assert response.status_code == 200, response.text
    return dict(response.json())


def fact_numbers(body: dict[str, Any]) -> set[Any]:
    prompt = body["debug"]["masked_prompt"]
    values = [line.split(" | ", 2)[2] for line in prompt.splitlines() if line.startswith("fact_")]
    return {n for v in values for n in numbers_in(v)}


def test_the_answer_lists_each_scenario_with_the_engines_numbers(world: World) -> None:
    quote = world.quote()
    stress = world.call("GET", f"/quotes/{quote['quote_id']}/stress?drops=5,10,15,20").json()
    body = ask(world, "What if the taka drops 10%?", quote_id=quote["quote_id"])
    text = body["reply"]
    assert text.startswith("Currency-drop stress test for GBP 10,000.00")
    assert stress["baseline"]["display"]["parent_pays"] in text
    for row in stress["scenarios"]:
        assert row["drop_pct"] in text and row["display"]["parent_pays"] in text
        assert row["display"]["extra"] in text
    assert "not a forecast" in text and "Indicative" in text
    assert body["guard"]["status"] == "passed"
    assert set(numbers_in(text)) <= fact_numbers(body)
    assert body["proposed_actions"] == []


def test_a_percentage_the_person_names_is_included(world: World) -> None:
    quote = world.quote()
    text = ask(world, "what if the taka drops 12%", quote_id=quote["quote_id"])["reply"]
    assert "12%" in text


def test_without_a_quote_it_asks_for_one_instead_of_inventing_numbers(world: World) -> None:
    body = ask(world, "What if the taka drops 10%?")
    assert "quote" in body["reply"].lower()
    assert body["guard"]["status"] == "passed"
    assert body["task"] is None


def test_the_stress_test_creates_no_quote_no_payment_and_no_approval(world: World) -> None:
    quote = world.quote()
    before = len(world.audit_rows(action="quote.created"))
    ask(world, "Run a stress test", quote_id=quote["quote_id"])
    assert len(world.audit_rows(action="quote.created")) == before
    assert world.call("GET", "/payments").json()["items"] == []


def test_the_trained_reader_cannot_turn_it_into_something_else(tmp_path: Path) -> None:
    if load_reader("auto") is None:
        pytest.skip("the trained reader is not available")
    world = World(tmp_path, nlu_mode="auto")
    try:
        quote = world.quote()
        body = ask(world, "What if the taka drops 10%?", quote_id=quote["quote_id"])
        assert body["reply"].startswith("Currency-drop stress test")
        assert body["understanding"]["intent"] == "STRESS"
    finally:
        world.close()
