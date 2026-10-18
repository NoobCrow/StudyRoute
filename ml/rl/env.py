"""The dialogue simulator: a parent with a goal talks to the assistant through its real reader.

An episode starts with the parent's first sentence (what the assistant perceived of it comes from
the bank built by build_bank.py). Each turn the assistant chooses one of five actions (see
backend/app/ai/dialogue/state.py). The episode ends when the assistant builds the plan (RUN) or
the parent gives up. The reward trades the value of a correct plan against the cost of asking.

Nothing here touches money: RUN only builds a quote and a plan card.
"""

from __future__ import annotations

import gzip
import json
import random
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.dialogue.state import MAX_TURNS, Action, DialogueState, SlotState, legal_actions  # noqa: E402

BANK = ROOT / "ml" / "rl" / "bank" / "bank.jsonl.gz"
SUBSETS = {
    "PLAN": ([("A", "D"), ("A",), ("D",), ()], [0.45, 0.30, 0.08, 0.17]),
    "CADENCE": ([("A", "Mo"), ("A",), ("Mo",), ()], [0.50, 0.25, 0.10, 0.15]),
}
SLOT_OF = {"A": "amount", "D": "date", "Mo": "months"}


@dataclass(frozen=True)
class Rewards:
    correct_amount: float = 1.0
    wrong_amount: float = -2.0  # a wrong quote on screen is the worst outcome
    correct_date: float = 0.5  # a plan with the right deadline is worth more than one without
    wrong_date: float = -1.0
    correct_months: float = 0.5
    wrong_months: float = -1.0
    turn_cost: float = -0.05  # every question costs the parent a little time
    abandon: float = -0.5
    abandon_after: int = 4  # after this many assistant turns the parent may lose patience
    abandon_prob: float = 0.08
    mistaken_no: float = 0.03  # the parent says "no" to a correct read-back this often


def load_bank(path: Path = BANK) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def split_bank(bank: list[dict]) -> dict[str, list[dict]]:
    """Disjoint goals: 70% train, 10% validation, 20% test (by position, the bank is shuffled)."""
    n = len(bank)
    return {
        "train": bank[: int(0.7 * n)],
        "val": bank[int(0.7 * n) : int(0.8 * n)],
        "test": bank[int(0.8 * n) :],
    }


def _slot(obs: dict) -> SlotState:
    return SlotState(obs["present"], obs["conflict"], obs["source"], obs["conf"])


@dataclass
class Episode:
    goal: dict
    answers: dict
    belief: dict[str, tuple[object, SlotState]]
    state: DialogueState
    asked_log: list[str] = field(default_factory=list)
    confirms: int = 0
    extra_amount: bool = False  # the latest amount read came from a message with several amounts
    done: bool = False


class DialogueEnv:
    def __init__(self, bank: list[dict], rewards: Rewards | None = None, seed: int = 0) -> None:
        self.bank = bank
        self.rewards = rewards or Rewards()
        self.rng = random.Random(seed)
        self.episode: Episode | None = None

    # --- the parent ---------------------------------------------------------------------------
    def reset(self, index: int | None = None) -> DialogueState:
        entry = self.bank[index if index is not None else self.rng.randrange(len(self.bank))]
        goal = entry["goal"]
        subsets, weights = SUBSETS[goal["task"]]
        wanted = self.rng.choices(subsets, weights)[0]
        first = self.rng.choice([f for f in entry["first"] if tuple(f["subset"]) == wanted])
        belief = {
            name: (first["slots"][name]["value"], _slot(first["slots"][name]))
            for name in ("amount", "date", "months")
        }
        state = DialogueState(
            task=goal["task"],
            amount=belief["amount"][1],
            date=belief["date"][1],
            months=belief["months"][1],
            intent_confidence=first["intent_conf"],
            extra_amount=first["amount_spans"] >= 2,
        )
        self.episode = Episode(
            goal, entry["answers"], belief, state, extra_amount=first["amount_spans"] >= 2
        )
        return state

    def _truth(self, slot: str) -> object:
        goal = self.episode.goal  # type: ignore[union-attr]
        if slot == "amount":
            return [goal["amount_minor"], goal["currency"]]
        return goal["due_date"] if slot == "date" else goal["months"]

    def _relevant(self) -> tuple[str, ...]:
        task = self.episode.goal["task"]  # type: ignore[union-attr]
        return ("amount", "date") if task == "PLAN" else ("amount", "months")

    def _wrong_slots(self) -> list[str]:
        ep = self.episode
        assert ep is not None
        return [
            s
            for s in self._relevant()
            if ep.belief[s][1].present and ep.belief[s][0] != self._truth(s)
        ]

    def _hear(self, slot: str) -> None:
        """The parent answers about one slot; the assistant perceives it through its reader."""
        ep = self.episode
        assert ep is not None
        if self._truth(slot) is None:  # "no deadline"
            ep.belief[slot] = (None, SlotState())
            if slot == "date":
                ep.state = replace(ep.state, date_skipped=True)
            return
        answer = self.rng.choice(ep.answers[slot])
        obs = answer["slots"][slot]
        ep.belief[slot] = (obs["value"], _slot(obs))
        if slot == "amount":
            ep.extra_amount = answer["amount_spans"] >= 2

    # --- one assistant turn -------------------------------------------------------------------
    def step(self, action: Action) -> tuple[DialogueState, float, bool, dict]:
        ep = self.episode
        assert ep is not None and not ep.done
        r = self.rewards
        state = ep.state
        if not legal_actions(state)[action]:
            raise ValueError(f"illegal action {action.name} in {state}")
        if action == Action.RUN:
            return self._run()
        reward = r.turn_cost
        asked = list(state.asked)
        if action in (Action.ASK_AMOUNT, Action.ASK_DATE, Action.ASK_MONTHS):
            slot = {
                Action.ASK_AMOUNT: "amount",
                Action.ASK_DATE: "date",
                Action.ASK_MONTHS: "months",
            }[action]
            asked[("amount", "date", "months").index(slot)] = True
            self._hear(slot)
            ep.state = replace(ep.state, confirmed=False)
        else:  # CONFIRM: read the values back
            ep.confirms += 1
            wrong = self._wrong_slots()
            if not wrong and self.rng.random() >= r.mistaken_no:
                for slot in self._relevant():
                    value, st = ep.belief[slot]
                    if st.present:
                        ep.belief[slot] = (value, SlotState(True, False, "earlier", 1.0))
                ep.extra_amount = False
                ep.state = replace(ep.state, confirmed=True)
            elif wrong:
                self._hear(wrong[0])
                ep.state = replace(ep.state, confirmed=False)
        turns = state.turns + 1
        ep.state = replace(
            ep.state,
            amount=ep.belief["amount"][1],
            date=ep.belief["date"][1],
            months=ep.belief["months"][1],
            turns=turns,
            asked=tuple(asked),
            extra_amount=ep.extra_amount,
        )
        if turns >= 12 or (turns > r.abandon_after and self.rng.random() < r.abandon_prob):
            ep.done = True
            return (
                ep.state,
                reward + r.abandon,
                True,
                {"abandoned": True, "wrong_plan": False, "success": False},
            )
        return ep.state, reward, False, {}

    def _run(self) -> tuple[DialogueState, float, bool, dict]:
        ep = self.episode
        assert ep is not None
        r = self.rewards
        reward = 0.0
        wrong = self._wrong_slots()
        if "amount" in wrong:
            reward += r.wrong_amount
        else:
            reward += r.correct_amount
        if ep.goal["task"] == "PLAN":
            date_state = ep.belief["date"][1]
            if "date" in wrong:
                reward += r.wrong_date
            elif date_state.present and ep.goal["due_date"] is not None:
                reward += r.correct_date
        else:
            reward += r.wrong_months if "months" in wrong else r.correct_months
        ep.done = True
        info = {
            "abandoned": False,
            "wrong_plan": bool(wrong),
            "success": not wrong and ep.belief["amount"][1].present,
        }
        return ep.state, reward, True, info


__all__ = ["MAX_TURNS", "Action", "DialogueEnv", "Rewards", "load_bank", "split_bank"]
