"""The safety rules of the dialogue policy are plain code, and they hold in every state.

The network may rank actions; it may never pick one these rules forbid. So the rules are checked
exhaustively over a grid of states, not sampled.
"""

from __future__ import annotations

import itertools

from app.ai.dialogue.state import (
    ACTIONS,
    FEATURES,
    MAX_TURNS,
    Action,
    DialogueState,
    SlotState,
    features,
    legal_actions,
)

PRESENT = SlotState(True, False, "both", 0.99)
MISSING = SlotState()
CONFLICT = SlotState(conflict=True)
SLOT_CHOICES = (MISSING, PRESENT, CONFLICT)


def grid() -> list[DialogueState]:
    states = []
    for task, amount, date, months in itertools.product(("PLAN", "CADENCE"), *[SLOT_CHOICES] * 3):
        for confirmed, skipped, turns, extra in itertools.product(
            (False, True), (False, True), (0, 2, MAX_TURNS - 1, MAX_TURNS + 3), (False, True)
        ):
            states.append(
                DialogueState(task, amount, date, months, 0.9, confirmed, skipped, turns, extra)
            )
    return states


STATES = grid()


def test_there_is_always_something_legal_to_do() -> None:
    for state in STATES:
        assert any(legal_actions(state)), state


def test_nothing_is_planned_while_the_amount_is_missing_or_read_two_ways() -> None:
    for state in STATES:
        if not state.amount.present or state.amount.conflict:
            legal = legal_actions(state)
            assert not legal[Action.RUN] and not legal[Action.CONFIRM], state
            assert legal[Action.ASK_AMOUNT], state


def test_a_send_plan_needs_its_period_and_a_payment_plan_needs_its_date_settled() -> None:
    for state in STATES:
        if not (state.amount.present and not state.amount.conflict):
            continue
        legal = legal_actions(state)
        if state.task == "CADENCE" and not (state.months.present and not state.months.conflict):
            assert not legal[Action.RUN] and legal[Action.ASK_MONTHS], state
        if state.task == "PLAN" and state.date.conflict:
            assert not legal[Action.RUN] and legal[Action.ASK_DATE], state


def test_a_value_that_was_already_confirmed_is_not_confirmed_again() -> None:
    for state in STATES:
        if state.confirmed:
            assert not legal_actions(state)[Action.CONFIRM], state


def test_the_policy_must_stop_confirming_when_it_runs_out_of_turns() -> None:
    for state in STATES:
        if state.turns >= MAX_TURNS - 1:
            assert not legal_actions(state)[Action.CONFIRM], state


def test_a_missing_amount_is_asked_for_only_when_it_is_actually_missing() -> None:
    state = DialogueState("PLAN", amount=PRESENT, date=MISSING)
    assert not legal_actions(state)[Action.ASK_AMOUNT]
    assert legal_actions(state)[Action.ASK_DATE] and legal_actions(state)[Action.RUN]


def test_once_the_person_said_there_is_no_deadline_the_date_is_not_asked_again() -> None:
    state = DialogueState("PLAN", amount=PRESENT, date_skipped=True)
    assert not legal_actions(state)[Action.ASK_DATE] and legal_actions(state)[Action.RUN]


def test_features_have_a_fixed_length_and_stay_between_zero_and_one() -> None:
    assert len(ACTIONS) == 5
    for state in STATES[:: max(1, len(STATES) // 400)]:
        values = features(state)
        assert len(values) == FEATURES
        assert all(0.0 <= v <= 1.0 for v in values), (state, values)


def test_the_amount_is_always_asked_for_first() -> None:
    for state in STATES:
        if not state.amount.present or state.amount.conflict:
            legal = legal_actions(state)
            assert legal == [True, False, False, False, False], state


def test_nothing_is_read_back_until_every_value_is_known() -> None:
    for state in STATES:
        legal = legal_actions(state)
        if state.task == "PLAN" and not state.date.present and not state.date_skipped:
            assert not legal[Action.CONFIRM], state
