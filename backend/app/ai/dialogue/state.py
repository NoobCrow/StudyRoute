"""What the dialogue policy sees, what it may do, and nothing else.

The policy is a small neural network trained by reinforcement learning (``ml/rl/``). It chooses
how the assistant should proceed with a payment request that may be incomplete or uncertain:

* ASK_AMOUNT, ASK_DATE, ASK_MONTHS: ask for the one value that is missing or unclear;
* CONFIRM: read the understood values back and ask a yes or no question;
* RUN: build the plan.

None of these moves money. RUN only builds a quote and a plan card; the person still creates the
draft and a human still approves with MFA. And the network is never trusted with the rules: the
legal actions are computed here, by plain code, from the state. The network can only rank them.
Training and the API both import this file, so they cannot disagree about the state or the rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

SLOTS = ("amount", "date", "months")
MAX_TURNS = 6  # after this many assistant turns the policy must run or ask for what is required


class Action(IntEnum):
    ASK_AMOUNT = 0
    ASK_DATE = 1
    ASK_MONTHS = 2
    CONFIRM = 3
    RUN = 4


ACTIONS = tuple(Action)
SOURCES = ("both", "model", "rules", "earlier")  # who read the value: see Understanding


@dataclass(frozen=True)
class SlotState:
    present: bool = False  # a value is held
    conflict: bool = False  # the rule reader and the model read it differently (value left empty)
    source: str | None = None  # one of SOURCES when present
    confidence: float = 0.0  # the model's confidence in the words it marked (0 when unknown)


@dataclass(frozen=True)
class DialogueState:
    task: str  # "PLAN" or "CADENCE"
    amount: SlotState = field(default_factory=SlotState)
    date: SlotState = field(default_factory=SlotState)
    months: SlotState = field(default_factory=SlotState)
    intent_confidence: float = 1.0
    confirmed: bool = False  # the person said "yes" to a read-back of these values
    date_skipped: bool = False  # the person said there is no deadline
    turns: int = 0  # assistant turns so far in this task
    extra_amount: bool = False  # the message mentions more than one amount: which one is meant?
    asked: tuple[bool, bool, bool] = (False, False, False)  # amount, date, months already asked

    def slot(self, name: str) -> SlotState:
        return getattr(self, name)  # type: ignore[no-any-return]


def _amount_ok(state: DialogueState) -> bool:
    return state.amount.present and not state.amount.conflict


def legal_actions(state: DialogueState) -> list[bool]:
    """Which actions are allowed. This is the safety rule: it does not depend on the network.

    The conversation always goes in a sensible order: the amount first, then the optional date (or
    the period of a send plan), and a read-back only once every value is known.
    """
    cadence = state.task == "CADENCE"
    amount_ok = _amount_ok(state)
    months_ok = state.months.present and not state.months.conflict
    date_ok = state.date.conflict is False
    ready = amount_ok and (months_ok if cadence else date_ok)
    forced = state.turns >= MAX_TURNS - 1
    date_settled = cadence or state.date.present or state.date_skipped
    ask_amount = not amount_ok
    ask_date = (
        amount_ok
        and not cadence
        and (
            state.date.conflict
            or (not state.date.present and not state.date_skipped and not forced)
        )
    )
    ask_months = amount_ok and cadence and not months_ok
    confirm = ready and date_settled and not state.confirmed and not forced
    run = ready
    legal = [ask_amount, ask_date, ask_months, confirm, run]
    return legal if any(legal) else [False, False, False, False, True]


def features(state: DialogueState) -> list[float]:
    """The state as numbers for the network."""
    out: list[float] = []
    for name in SLOTS:
        slot = state.slot(name)
        out += [float(slot.present), float(slot.conflict)]
        out += [float(slot.source == s) for s in SOURCES]
        out.append(float(slot.confidence))
    out += [
        float(state.task == "CADENCE"),
        float(state.intent_confidence),
        float(state.confirmed),
        float(state.date_skipped),
        float(state.extra_amount),
        min(state.turns, MAX_TURNS) / MAX_TURNS,
        *[float(a) for a in state.asked],
    ]
    return out


FEATURES = len(features(DialogueState("PLAN")))
