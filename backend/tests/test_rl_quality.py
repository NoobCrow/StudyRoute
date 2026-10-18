"""A quality floor for the shipped dialogue policy, and a guard against a stale report.

The simulator is an assumption (see docs/AI_RL.md), so this only checks what the training claims:
on goals the policy never trained on, it beats the old behaviour (plan as soon as the amount is
known) by a clear margin, and the report and manifest describe the policy that is shipped.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from app.ai.dialogue.policy import POLICY_DIR, load_policy

ROOT = Path(__file__).resolve().parents[2]
RL = ROOT / "ml" / "rl"
policy = load_policy("auto")
if policy is None or not (RL / "bank" / "bank.jsonl.gz").is_file():  # pragma: no cover
    pytest.skip("the dialogue policy or its simulator bank is not present", allow_module_level=True)
sys.path.insert(0, str(RL))

import env as sim  # noqa: E402
import policies  # noqa: E402


@pytest.fixture(scope="module")
def validation_goals() -> list[dict]:
    return sim.split_bank(sim.load_bank())["val"]


def test_the_shipped_policy_beats_planning_as_soon_as_the_amount_is_known(validation_goals) -> None:  # type: ignore[no-untyped-def]
    rewards = sim.Rewards()
    learned = policies.evaluate(
        lambda state, legal, rng: policy.choose(state).action,
        validation_goals,
        rewards,
        1200,
        seed=5,
    )
    before = policies.evaluate(policies.act_when_ready, validation_goals, rewards, 1200, seed=5)
    assert learned.mean >= before.mean + 0.10, (learned.mean, before.mean)
    assert learned.wrong_plan <= before.wrong_plan


def test_it_asks_for_a_missing_amount_and_a_missing_deadline(validation_goals) -> None:  # type: ignore[no-untyped-def]
    result = policies.evaluate(
        lambda state, legal, rng: policy.choose(state).action,
        validation_goals, sim.Rewards(), 600, seed=6,
    )  # fmt: skip
    assert result.action_counts["ASK_AMOUNT"] > 0 and result.action_counts["ASK_DATE"] > 0


def test_the_manifest_describes_the_shipped_weights_and_the_bank_it_learned_from() -> None:
    manifest = json.loads((POLICY_DIR / "manifest.json").read_text(encoding="utf-8"))
    bank = hashlib.sha256((RL / "bank" / "bank.jsonl.gz").read_bytes()).hexdigest()
    assert manifest["observation_bank_sha256"] == bank, "retrain: the bank has changed since"
    assert manifest["selected_on"].startswith("validation")


def test_the_evaluation_report_describes_the_shipped_policy() -> None:
    report = json.loads(
        (ROOT / "submission" / "evidence" / "ai_rl_evaluation.json").read_text("utf-8")
    )
    assert report["policy_sha256"] == policy.sha256, (
        "docs/AI_RL_EVALUATION.md is stale: run ml/rl/evaluate_rl.py after exporting a policy"
    )
