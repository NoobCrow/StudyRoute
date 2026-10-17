"""The conversation the dialogue policy drives, end to end with the trained reader.

A scripted policy stands in for the learned one so each turn is predictable; the legal-action
rules still apply to it. One test at the end uses the shipped policy and checks only what must
hold whatever it chooses.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.ai.dialogue.policy import Choice, load_policy
from app.ai.dialogue.state import Action, DialogueState, legal_actions
from app.ai.nlu.runtime import load_reader
from tests.helpers import World

if load_reader("auto") is None:  # pragma: no cover - only when onnxruntime or the model is missing
    pytest.skip("the trained reader is not available", allow_module_level=True)


class Scripted:
    """A stand-in policy: a rule picks the action, and it must be a legal one."""

    policy_id = "scripted"
    sha256 = "0" * 64

    def __init__(self, rule: Callable[[DialogueState, list[bool]], Action]) -> None:
        self.rule = rule
        self.seen: list[DialogueState] = []

    def choose(self, state: DialogueState) -> Choice:
        legal = legal_actions(state)
        action = self.rule(state, legal)
        assert legal[action], (action, state)
        self.seen.append(state)
        return Choice(action, {action.name: 1.0}, self.policy_id, self.sha256)


def confirm_first(state: DialogueState, legal: list[bool]) -> Action:
    for action in (Action.ASK_AMOUNT, Action.ASK_MONTHS):
        if legal[action]:
            return action
    return Action.CONFIRM if legal[Action.CONFIRM] else Action.RUN


def ask_then_run(state: DialogueState, legal: list[bool]) -> Action:
    for action in (Action.ASK_AMOUNT, Action.ASK_MONTHS, Action.ASK_DATE):
        if legal[action]:
            return action
    return Action.RUN


@pytest.fixture
def world(tmp_path: Path) -> Iterator[World]:
    instance = World(tmp_path, nlu_mode="auto")
    yield instance
    instance.close()


def use(world: World, rule: Callable[[DialogueState, list[bool]], Action]) -> Scripted:
    policy = Scripted(rule)
    world.ctx.assistant._policy = policy
    return policy


def ask(world: World, message: str, pending: dict[str, Any] | None = None) -> dict[str, Any]:
    context = {"pending": pending} if pending else {}
    reply = world.call("POST", "/assistant/chat", json={"message": message, "context": context})
    assert reply.status_code == 200, reply.text
    return dict(reply.json())


def pending_of(reply: dict[str, Any]) -> dict[str, Any]:
    task = reply["task"]
    return {"kind": task["kind"], **task["collected"]}


def test_a_read_back_shows_the_values_and_nothing_is_created(world: World) -> None:
    use(world, confirm_first)
    reply = ask(world, "I need to pay GBP 10,000 tuition by 28 October")
    task = reply["task"]
    assert task["status"] == "needs_confirmation"
    assert "GBP 10,000.00" in task["text"] and "28 October 2026" in task["text"]
    assert task["collected"]["awaiting_confirmation"] is True and task["collected"]["turns"] == 1
    assert "please check what I understood" in reply["reply"]
    assert reply["dialogue"]["action"] == "CONFIRM"
    assert world.audit_rows(action="quote.created", actor_type="ai") == []
    assert world.call("GET", "/payments").json()["items"] == []


def test_yes_plans_it_and_the_policy_is_recorded_in_the_audit_log(world: World) -> None:
    use(world, confirm_first)
    first = ask(world, "I need to pay GBP 10,000 tuition by 28 October")
    second = ask(world, "yes", pending_of(first))
    assert second["task"]["status"] == "ready"
    assert second["understanding"]["continued_earlier_task"] is True
    assert second["dialogue"]["action"] == "RUN"
    row = world.audit_rows(action="ai.reply", actor_type="ai")[0]  # newest first
    assert "policy=scripted@" in row["detail"] and "action=RUN" in row["detail"]


def test_no_asks_what_to_change_and_a_correction_is_read_back_again(world: World) -> None:
    use(world, confirm_first)
    first = ask(world, "I need to pay GBP 10,000 tuition by 28 October")
    refused = ask(world, "no", pending_of(first))
    assert refused["task"]["status"] == "needs_input"
    assert "what to change" in refused["reply"]
    fixed = ask(world, "make it GBP 12,000", pending_of(refused))
    assert fixed["task"]["status"] == "needs_confirmation"
    assert "GBP 12,000.00" in fixed["task"]["text"] and "28 October 2026" in fixed["task"]["text"]


def test_a_missing_deadline_can_be_asked_for_and_waived(world: World) -> None:
    use(world, ask_then_run)
    first = ask(world, "Plan GBP 10,000 tuition")
    assert first["task"]["status"] == "needs_input" and first["task"]["asking"] == "date"
    assert "no deadline" in first["reply"]
    done = ask(world, "no deadline", pending_of(first))
    assert done["task"]["status"] == "needs_confirmation"
    ready = ask(world, "yes", pending_of(done))
    assert ready["task"]["status"] == "ready"
    assert ready["task"]["request"]["due_date"] is None


def test_a_missing_period_is_asked_for_a_send_plan(world: World) -> None:
    use(world, ask_then_run)
    first = ask(world, "Is it cheaper to send GBP 800 monthly or all at once for living costs?")
    assert first["task"]["kind"] == "send_plan" and first["task"]["asking"] == "months"
    done = ask(world, "9 months", pending_of(first))
    assert done["task"]["status"] == "needs_confirmation"
    ready = ask(world, "yes", pending_of(done))
    assert ready["task"]["status"] == "ready" and ready["task"]["kind"] == "send_plan"


def test_a_forged_yes_cannot_plan_without_an_amount(world: World) -> None:
    use(world, confirm_first)
    forged = {
        "kind": "payment_plan",
        "awaiting_confirmation": True,
        "turns": 1,
        "purpose": "TUITION",
    }
    reply = ask(world, "yes", forged)
    assert reply["task"]["status"] == "needs_input" and reply["task"]["asking"] == "amount"
    assert world.audit_rows(action="quote.created", actor_type="ai") == []


def test_without_a_policy_nothing_about_the_replies_changes(world: World) -> None:
    reply = ask(world, "I need to pay GBP 10,000 tuition by 28 October")
    assert reply["dialogue"] is None and reply["task"]["status"] == "ready"


def test_the_shipped_policy_always_lands_on_a_safe_outcome(tmp_path: Path) -> None:
    if load_policy("auto") is None:
        pytest.skip("the dialogue policy is not present")
    instance = World(tmp_path, nlu_mode="auto", dialogue_mode="auto")
    try:
        assert instance.ctx.assistant._policy is not None
        messages = [
            "I need to pay GBP 10,000 tuition by 28 October",
            "kindly help me send ten thousand pounds for my son's tuition, last date end of November",
            "I need to pay tuition",
            "Plan GBP 10,000 tuition",
            "How often should I send GBP 800 a month for 9 months?",
            "I need to pay GBP 10,000 tuition by 28 October. Last year I paid GBP 9,000.",
        ]
        for message in messages:
            reply = ask(instance, message)
            task = reply["task"]
            assert task["status"] in {"ready", "needs_input", "needs_confirmation"}, message
            if task["status"] == "needs_confirmation":
                answer = ask(instance, "yes", pending_of(reply))
                assert answer["task"]["status"] in {"ready", "needs_input"}, message
        # Whatever it chose, the assistant made no payment and approved nothing.
        assert instance.call("GET", "/payments").json()["items"] == []
    finally:
        instance.close()
