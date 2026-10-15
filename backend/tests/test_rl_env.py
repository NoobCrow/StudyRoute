"""The reinforcement-learning simulator: its reward accounting and its rules, on a hand-made bank.

The bank here has no model in it (the values the assistant "perceives" are written out), so these
tests check the simulator and the baseline policies, not the reader.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

from app.ai.dialogue.state import Action, legal_actions

RL = Path(__file__).resolve().parents[2] / "ml" / "rl"
if not (RL / "env.py").is_file():  # pragma: no cover - a stripped checkout
    pytest.skip("the reinforcement-learning code is not present", allow_module_level=True)
sys.path.insert(0, str(RL))

import env as sim  # noqa: E402
import policies  # noqa: E402

GOAL = {
    "task": "PLAN",
    "currency": "GBP",
    "amount_minor": 1_000_000,
    "due_date": "2026-11-28",
    "months": None,
}
AMOUNT = [1_000_000, "GBP"]


def slot(
    value: object,
    *,
    present: bool = True,
    source: str = "both",
    conf: float = 0.99,
    conflict: bool = False,
) -> dict:
    return {
        "value": value,
        "present": present,
        "conflict": conflict,
        "source": source if present else None,
        "conf": conf,
    }


MISSING = slot(None, present=False, conf=0.0)


def first(subset: list[str], amount: dict, date: dict, spans: int = 1) -> dict:
    return {"subset": subset, "text": "x", "intent": "PLAN", "intent_conf": 0.99, "attack": False,
            "amount_spans": spans, "slots": {"amount": amount, "date": date, "months": MISSING}}  # fmt: skip


def bank_with(
    first_message: dict, answers: dict | None = None, goal: dict | None = None
) -> list[dict]:
    goal = goal or GOAL
    subset = tuple(first_message["subset"])
    entry = {"goal": goal, "first": [first_message] * 2, "answers": answers or {}}
    # the environment picks a first message that matches the parent's chosen subset
    entry["first"] = [
        {**first_message, "subset": list(s)} for s in sim.SUBSETS[goal["task"]][0] for _ in range(2)
    ]
    del subset
    return [entry]


def run(bank: list[dict], rewards: sim.Rewards, actions: list[Action]) -> list[tuple[float, bool]]:
    environment = sim.DialogueEnv(bank, rewards, seed=1)
    environment.reset(0)
    out = []
    for action in actions:
        _, reward, done, _ = environment.step(action)
        out.append((reward, done))
    return out


def test_planning_with_everything_right_earns_the_full_reward() -> None:
    bank = bank_with(first(["A", "D"], slot(AMOUNT), slot("2026-11-28")))
    # the parent may or may not have mentioned the date; force the amount and date to be known
    environment = sim.DialogueEnv(bank, sim.Rewards(), seed=1)
    state = environment.reset(0)
    assert state.amount.present
    environment.episode.belief["date"] = ("2026-11-28", sim.SlotState(True, False, "both", 0.99))  # type: ignore[union-attr]
    _, reward, done, info = environment.step(Action.RUN)
    assert done and reward == pytest.approx(1.5) and info["success"] and not info["wrong_plan"]


def test_a_wrong_amount_on_the_plan_is_punished_hard() -> None:
    wrong = slot([2_000_000, "GBP"])
    bank = bank_with(first(["A", "D"], wrong, slot("2026-11-28")))
    environment = sim.DialogueEnv(bank, sim.Rewards(), seed=1)
    environment.reset(0)
    environment.episode.belief["date"] = ("2026-11-28", sim.SlotState(True, False, "both", 0.99))  # type: ignore[union-attr]
    _, reward, _, info = environment.step(Action.RUN)
    assert reward == pytest.approx(-2.0 + 0.5) and info["wrong_plan"] and not info["success"]


def test_every_question_costs_the_parent_a_little_time() -> None:
    answers = {
        "amount": [
            {
                "slots": {"amount": slot(AMOUNT), "date": MISSING, "months": MISSING},
                "amount_spans": 1,
            }
        ]
    }
    bank = bank_with(first(["D"], MISSING, MISSING), answers)
    environment = sim.DialogueEnv(bank, sim.Rewards(turn_cost=-0.05), seed=1)
    state = environment.reset(0)
    legal = legal_actions(state)
    if not legal[Action.ASK_AMOUNT]:
        pytest.skip("this parent already gave an amount")
    state, reward, done, _ = environment.step(Action.ASK_AMOUNT)
    assert reward == pytest.approx(-0.05) and not done and state.turns == 1 and state.asked[0]
    assert state.amount.present


def test_confirming_a_correct_value_makes_it_certain_and_a_wrong_one_is_corrected() -> None:
    answers = {
        "amount": [
            {
                "slots": {"amount": slot(AMOUNT), "date": MISSING, "months": MISSING},
                "amount_spans": 1,
            }
        ]
    }
    bank = bank_with(first(["A", "D"], slot([2_000_000, "GBP"]), slot("2026-11-28")), answers)
    environment = sim.DialogueEnv(bank, sim.Rewards(mistaken_no=0.0), seed=1)
    environment.reset(0)
    environment.episode.belief["date"] = ("2026-11-28", sim.SlotState(True, False, "both", 0.99))  # type: ignore[union-attr]
    state, _, _, _ = environment.step(
        Action.CONFIRM
    )  # the amount is wrong, so the parent corrects it
    assert not state.confirmed and environment.episode.belief["amount"][0] == AMOUNT  # type: ignore[union-attr]
    state, _, _, _ = environment.step(Action.CONFIRM)  # now everything is right
    assert state.confirmed and state.amount.confidence == 1.0 and state.amount.source == "earlier"


def test_the_simulator_refuses_an_illegal_action() -> None:
    bank = bank_with(first(["D"], MISSING, MISSING))
    environment = sim.DialogueEnv(bank, sim.Rewards(), seed=1)
    environment.reset(0)
    with pytest.raises(ValueError, match="illegal"):
        environment.step(Action.RUN)  # no amount yet


def test_a_parent_who_has_no_deadline_says_so_when_asked() -> None:
    goal = {**GOAL, "due_date": None}
    bank = bank_with(first(["A"], slot(AMOUNT), MISSING), goal=goal)
    environment = sim.DialogueEnv(bank, sim.Rewards(), seed=1)
    state = environment.reset(0)
    assert legal_actions(state)[Action.ASK_DATE]
    state, _, _, _ = environment.step(Action.ASK_DATE)
    assert state.date_skipped and not legal_actions(state)[Action.ASK_DATE]


def test_the_hand_written_policies_only_choose_legal_actions() -> None:
    bank = bank_with(first(["A", "D"], slot(AMOUNT), slot("2026-11-28")))
    rng = random.Random(0)
    for policy in (policies.act_when_ready, policies.confirm_always, policies.ask_everything,
                   policies.threshold_rule(0.99, True, True), policies.random_legal):  # fmt: skip
        result = policies.evaluate(policy, bank, sim.Rewards(), 20, seed=3)
        assert len(result.returns) == 20
    assert rng.random() >= 0
