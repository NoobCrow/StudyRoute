"""Hand-written dialogue policies to compare the learned one against, and the evaluation loop.

Every policy is a function (state, legal, rng) -> Action and may only pick a legal action.
"""

from __future__ import annotations

import random
import statistics
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ml" / "rl"), str(ROOT / "backend")]

from app.ai.dialogue.state import DialogueState, legal_actions  # noqa: E402
from env import Action, DialogueEnv, Rewards  # noqa: E402

Policy = Callable[[DialogueState, list[bool], random.Random], Action]


def _first(legal: list[bool], order: tuple[Action, ...]) -> Action:
    return next(a for a in order if legal[a])


ASKS = (Action.ASK_AMOUNT, Action.ASK_MONTHS, Action.ASK_DATE)


def act_when_ready(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
    """How the assistant behaved before: plan as soon as the amount is known; ask only if forced."""
    return _first(legal, (Action.RUN, *ASKS))


def confirm_always(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
    """Ask for what is required, read everything back, then plan."""
    for action in (Action.ASK_AMOUNT, Action.ASK_MONTHS):
        if legal[action]:
            return action
    if state.date.conflict and legal[Action.ASK_DATE]:
        return Action.ASK_DATE
    return Action.CONFIRM if legal[Action.CONFIRM] else Action.RUN


def ask_everything(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
    """Ask for every missing value (the date too), read everything back, then plan."""
    return _first(
        legal, (Action.ASK_AMOUNT, Action.ASK_MONTHS, Action.ASK_DATE, Action.CONFIRM, Action.RUN)
    )


def threshold_rule(tau: float, ask_date: bool = True, use_extra: bool = False) -> Policy:
    """Ask for what is missing; read back only values that were read with low confidence or by
    one reader alone. A careful engineer's version of the problem, tuned on validation data."""

    def policy(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
        asks_date = ask_date or state.date.conflict
        order = (Action.ASK_AMOUNT, Action.ASK_MONTHS, *((Action.ASK_DATE,) if asks_date else ()))
        for action in order:
            if legal[action]:
                return action
        cadence = state.task == "CADENCE"
        slots = [state.amount, state.months if cadence else state.date]
        unsure = any(
            s.present and s.source != "earlier" and (s.source != "both" or s.confidence < tau)
            for s in slots
        )
        unsure = unsure or (use_extra and state.extra_amount and not state.confirmed)
        if unsure and legal[Action.CONFIRM]:
            return Action.CONFIRM
        return Action.RUN

    return policy


def random_legal(state: DialogueState, legal: list[bool], rng: random.Random) -> Action:
    return rng.choice([a for a in Action if legal[a]])


@dataclass
class Result:
    returns: list[float]
    success: float
    wrong_plan: float
    abandoned: float
    turns: float
    confirm_rate: float
    action_counts: dict[str, int]

    @property
    def mean(self) -> float:
        return statistics.fmean(self.returns)

    def ci(self, seed: int = 0, rounds: int = 1000) -> tuple[float, float]:
        rng = random.Random(seed)
        n = len(self.returns)
        means = sorted(statistics.fmean(rng.choices(self.returns, k=n)) for _ in range(rounds))
        return means[int(0.025 * rounds)], means[int(0.975 * rounds)]


def evaluate(
    policy: Policy, bank: list[dict], rewards: Rewards, episodes: int, seed: int
) -> Result:
    env = DialogueEnv(bank, rewards, seed=seed)
    rng = random.Random(seed + 1)
    returns: list[float] = []
    success = wrong = abandoned = confirms = 0
    turns = 0
    counts: dict[str, int] = {a.name: 0 for a in Action}
    for episode in range(episodes):
        state = env.reset(episode % len(bank))
        total, done, info = 0.0, False, {}
        while not done:
            legal = legal_actions(state)
            action = policy(state, legal, rng)
            counts[action.name] += 1
            state, reward, done, info = env.step(action)
            total += reward
        returns.append(total)
        success += info["success"]
        wrong += info["wrong_plan"]
        abandoned += info["abandoned"]
        confirms += env.episode.confirms > 0  # type: ignore[union-attr]
        turns += state.turns
    n = episodes
    return Result(returns, success / n, wrong / n, abandoned / n, turns / n, confirms / n, counts)
