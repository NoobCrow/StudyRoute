"""Measure the shipped dialogue policy against hand-written policies. Writes docs/AI_RL_EVALUATION.md.

    ml/.venv/Scripts/python ml/rl/evaluate_rl.py

All numbers are on the TEST goals of the simulator (goals never used for training or to pick a
run). The shipped policy is the exported JSON, run through the same NumPy code the API uses, so
what is measured is what ships. The simulator is an assumption, not a user study: read
docs/AI_RL.md before trusting a number.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "ml" / "runs" / "rl"
sys.path[:0] = [str(ROOT / "ml" / "rl"), str(ROOT / "backend")]

import policies as P  # noqa: E402
import torch  # noqa: E402
from app.ai.dialogue.policy import DialoguePolicy  # noqa: E402
from app.ai.dialogue.state import legal_actions  # noqa: E402
from env import DialogueEnv, Rewards, load_bank, split_bank  # noqa: E402
from train_dqn import build_net, greedy  # noqa: E402


def shipped(policy: DialoguePolicy) -> P.Policy:
    return lambda state, legal, rng: policy.choose(state).action


def net_policy(name: str) -> P.Policy:
    net = build_net()
    net.load_state_dict(torch.load(RUNS / name / "best.pt", map_location="cpu"))
    return greedy(net, torch.device("cpu"))


def best_rule(bank: list[dict], rewards: Rewards) -> tuple[str, P.Policy]:
    """The best hand-written threshold rule, chosen on VALIDATION goals."""
    best = (float("-inf"), "", P.act_when_ready)
    for tau in (0.0, 0.9, 0.95, 0.99, 0.999):
        for ask_date in (False, True):
            for use_extra in (False, True):
                rule = P.threshold_rule(tau, ask_date, use_extra)
                got = P.evaluate(rule, bank, rewards, 3 * len(bank), seed=11).mean
                if got > best[0]:
                    best = (
                        got,
                        f"tau {tau}, ask date {ask_date}, extra-amount signal {use_extra}",
                        rule,
                    )
    return best[1], best[2]


def first_decisions(policy: P.Policy, bank: list[dict], rewards: Rewards) -> dict[str, Counter]:
    """What the policy does first, by the situation it is in."""
    env = DialogueEnv(bank, rewards, seed=3)
    rng = random.Random(4)
    table: dict[str, Counter] = defaultdict(Counter)
    for episode in range(5 * len(bank)):
        state = env.reset(episode % len(bank))
        legal = legal_actions(state)
        slot = state.months if state.task == "CADENCE" else state.date
        if not state.amount.present or state.amount.conflict:
            where = "the amount is missing or read two ways"
        elif state.extra_amount:
            where = "the amount is read, but the message mentions another amount"
        elif state.amount.source == "model":
            where = "the amount is read by the model only (the rules did not find it)"
        elif not slot.present and not slot.conflict:
            where = "the amount is read; the date (or period) is missing"
        else:
            where = "everything needed is read by both readers"
        table[where][policy(state, legal, rng).name] += 1
    return table


def row(name: str, result: P.Result) -> str:
    lo, hi = result.ci()
    return (
        f"| {name} | {result.mean:+.3f} ({lo:+.3f} to {hi:+.3f}) | {100 * result.success:.1f}% | "
        f"{100 * result.wrong_plan:.1f}% | {result.turns:.2f} | {100 * result.confirm_rate:.0f}% | "
        f"{100 * result.abandoned:.1f}% |"
    )


def main() -> None:
    rewards = Rewards()
    banks = split_bank(load_bank())
    test, val = banks["test"], banks["val"]
    episodes = 5 * len(test)
    policy_file = DialoguePolicy()
    rule_name, rule = best_rule(val, rewards)
    candidates: dict[str, P.Policy] = {
        "random legal action": P.random_legal,
        "before: plan as soon as the amount is known": P.act_when_ready,
        "confirm every time (skip the optional date)": P.confirm_always,
        "ask for everything, confirm every time": P.ask_everything,
        f"best hand-written rule ({rule_name})": rule,
        "RL policy (shipped)": shipped(policy_file),
    }
    results = {
        name: P.evaluate(pol, test, rewards, episodes, seed=21) for name, pol in candidates.items()
    }

    seeds = {}
    for name in ("dm1", "dm2", "dm3"):
        if (RUNS / name / "best.pt").exists():
            seeds[name] = P.evaluate(net_policy(name), test, rewards, episodes, seed=21)

    sensitivity = {}
    for name, label, rw in (
        ("dm1", "default (wrong amount -2, turn -0.05)", rewards),
        ("dm_careful", "careful (wrong amount -10)", Rewards(wrong_amount=-10.0)),
        ("dm_lenient", "lenient (wrong amount -0.5)", Rewards(wrong_amount=-0.5)),
        ("dm_impatient", "impatient parent (turn -0.3)", Rewards(turn_cost=-0.3)),
    ):
        if not (RUNS / name / "best.pt").exists():
            continue
        sensitivity[label] = {
            "RL": P.evaluate(net_policy(name), test, rw, episodes, seed=21),
            "before": P.evaluate(P.act_when_ready, test, rw, episodes, seed=21),
            "ask all + confirm": P.evaluate(P.ask_everything, test, rw, episodes, seed=21),
        }
    behaviour = first_decisions(shipped(policy_file), test, rewards)
    curves = {n: json.loads((RUNS / n / "curve.json").read_text("utf-8")) for n in seeds}

    report = {
        "policy_id": policy_file.policy_id,
        "policy_sha256": policy_file.sha256,
        "episodes_per_policy": episodes,
        "test_goals": len(test),
        "rewards": rewards.__dict__,
        "results": {
            n: {
                "return": r.mean,
                "ci95": r.ci(),
                "success": r.success,
                "wrong_plan": r.wrong_plan,
                "turns": r.turns,
                "confirm_rate": r.confirm_rate,
                "abandoned": r.abandoned,
                "actions": r.action_counts,
            }
            for n, r in results.items()
        },
        "seeds": {
            n: {"return": r.mean, "wrong_plan": r.wrong_plan, "turns": r.turns}
            for n, r in seeds.items()
        },
        "sensitivity": {
            label: {
                k: {
                    "return": v.mean,
                    "wrong_plan": v.wrong_plan,
                    "turns": v.turns,
                    "confirm_rate": v.confirm_rate,
                }
                for k, v in d.items()
            }
            for label, d in sensitivity.items()
        },
        "behaviour": {k: dict(v) for k, v in behaviour.items()},
        "curves": curves,
    }
    evidence = ROOT / "submission" / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "ai_rl_evaluation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )

    out = [
        "# Reinforcement learning: the dialogue policy against hand-written policies",
        "",
        f"Generated by `ml/rl/evaluate_rl.py` from the shipped policy (`{policy_file.policy_id}`); do not "
        "edit by hand. Every number is on the **test goals of the simulator**, which were never used to "
        "train or to choose a run. The simulator is an assumption, not a user study: see "
        "[AI_RL.md](AI_RL.md) for what it assumes and what that means.",
        "",
        f"{episodes:,} simulated conversations per policy ({len(test):,} test goals, five parent "
        "personalities each). Return = the reward the policy was trained on: +1 for a correct plan, "
        "+0.5 for a correct deadline or period, -2 for a wrong amount, -1 for a wrong deadline or period, "
        "-0.05 for every question asked, -0.5 if the parent gives up. 95% bootstrap intervals.",
        "",
        "## Policies compared",
        "",
        "| Policy | Return | Correct plan | Wrong plan | Questions asked | Read back | Gave up |",
        "|---|---|---|---|---|---|---|",
        *[row(n, r) for n, r in results.items()],
        "",
        "The legal-action rules are the same for every policy: nobody may plan with the amount missing or "
        "read two ways.",
        "",
        "## What the learned policy does first",
        "",
        "Counted over the test conversations, by the situation at its first decision:",
        "",
        "| Situation | Plan | Confirm | Ask amount | Ask date | Ask period |",
        "|---|---|---|---|---|---|",
    ]
    for where, counts in sorted(behaviour.items()):
        n = sum(counts.values())
        cells = [
            f"{100 * counts.get(a, 0) / n:.0f}%"
            for a in ("RUN", "CONFIRM", "ASK_AMOUNT", "ASK_DATE", "ASK_MONTHS")
        ]
        out.append(f"| {where} (n = {n}) | " + " | ".join(cells) + " |")
    out += [
        "",
        "## Is it stable? Three training seeds",
        "",
        "| Run | Return | Wrong plan | Questions |",
        "|---|---|---|---|",
    ]
    for name, r in seeds.items():
        out.append(f"| {name} | {r.mean:+.3f} | {100 * r.wrong_plan:.1f}% | {r.turns:.2f} |")
    if seeds:
        spread = max(r.mean for r in seeds.values()) - min(r.mean for r in seeds.values())
        out.append(
            f"\nThe seeds differ by {spread:.3f} in return; the shipped policy is the one with the best "
            "validation return."
        )
    out += [
        "",
        "## Does it respond to what matters? Changing the reward",
        "",
        "Retrained with a different reward, each policy is compared with the two fixed behaviours under "
        "the same reward. A sensible policy asks and confirms more when a wrong plan costs more, and "
        "less when the parent's time costs more.",
        "",
        "| Reward | Policy | Return | Wrong plan | Questions | Read back |",
        "|---|---|---|---|---|---|",
    ]
    for label, group in sensitivity.items():
        for k, v in group.items():
            out.append(
                f"| {label} | {k} | {v.mean:+.3f} | {100 * v.wrong_plan:.1f}% | {v.turns:.2f} | "
                f"{100 * v.confirm_rate:.0f}% |"
            )
    out += [
        "",
        "## How to read this honestly",
        "",
        "* The parents are simulated, and the rewards are my choices. A policy trained on them is only as "
        "good as that assumption; the sensitivity table shows how much the behaviour depends on it.",
        "* What the policy perceives is real: every sentence went through the assistant's own reader "
        "and checks, so the noise (missing values, values read two ways, a second amount) is the real "
        "system's.",
        "* The policy cannot see whether a value is correct. It sees who read it, how sure the model "
        "was, whether the message mentioned another amount, and the turn count.",
        "* None of its actions moves money. The worst outcome is an extra question or a wrong quote card "
        "that the person reviews before creating a draft, and a human still approves.",
    ]
    (ROOT / "docs" / "AI_RL_EVALUATION.md").write_text(
        "\n".join(out) + "\n", encoding="utf-8", newline="\n"
    )
    for name, r in results.items():
        print(f"{name[:58]:58} {r.mean:+.3f}  wrong {100 * r.wrong_plan:.1f}%  turns {r.turns:.2f}")


if __name__ == "__main__":
    main()
