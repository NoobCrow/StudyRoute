"""Loading and running the dialogue policy: integrity, shape, and the mask that beats the network."""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path

import pytest

from app.ai.dialogue.policy import POLICY_DIR, DialoguePolicy, load_policy
from app.ai.dialogue.state import ACTIONS, FEATURES, Action, DialogueState, SlotState

PRESENT = SlotState(True, False, "both", 0.99)


def write_policy(directory: Path, *, favour: Action, shapes: tuple[int, ...] | None = None) -> None:
    """A policy that loves one action (a huge bias) whatever the state: the worst case for the mask."""
    sizes = shapes or (FEATURES, len(ACTIONS))
    layers = []
    for rows, cols in itertools.pairwise(sizes):
        bias = [0.0] * cols
        if cols == len(ACTIONS):
            bias[favour] = 1000.0
        layers.append({"w": [[0.0] * cols for _ in range(rows)], "b": bias})
    directory.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"layers": layers})
    (directory / "policy.json").write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    manifest = {"policy_id": "test-policy", "files": {"policy.json": digest}}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_the_network_cannot_plan_with_a_missing_amount_however_much_it_wants_to(
    tmp_path: Path,
) -> None:
    write_policy(tmp_path, favour=Action.RUN)
    policy = DialoguePolicy(tmp_path)
    choice = policy.choose(DialogueState("PLAN"))  # nothing is known
    assert choice.action is Action.ASK_AMOUNT
    assert "RUN" not in choice.q_values and "CONFIRM" not in choice.q_values


def test_a_policy_that_loves_confirming_still_may_not_confirm_twice(tmp_path: Path) -> None:
    write_policy(tmp_path, favour=Action.CONFIRM)
    policy = DialoguePolicy(tmp_path)
    ready = DialogueState("PLAN", amount=PRESENT, date=PRESENT)
    assert policy.choose(ready).action is Action.CONFIRM
    assert (
        policy.choose(DialogueState("PLAN", amount=PRESENT, date=PRESENT, confirmed=True)).action
        is Action.RUN
    )


def test_a_tampered_policy_file_is_not_used(tmp_path: Path) -> None:
    write_policy(tmp_path, favour=Action.RUN)
    (tmp_path / "policy.json").write_text(
        (tmp_path / "policy.json").read_text() + " ", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="SHA-256"):
        DialoguePolicy(tmp_path)
    assert load_policy("auto", tmp_path) is None


def test_a_policy_that_does_not_fit_the_current_state_is_refused(tmp_path: Path) -> None:
    write_policy(tmp_path, favour=Action.RUN, shapes=(FEATURES + 3, len(ACTIONS)))
    with pytest.raises(ValueError, match="does not fit"):
        DialoguePolicy(tmp_path)


def test_switched_off_or_missing_means_no_policy(tmp_path: Path) -> None:
    assert load_policy("off") is None
    assert load_policy("auto", tmp_path / "nowhere") is None


def test_the_shipped_policy_loads_and_is_deterministic() -> None:
    policy = load_policy("auto")
    if policy is None:
        pytest.skip("the dialogue policy is not present")
    state = DialogueState("PLAN", amount=PRESENT, date=SlotState())
    first, second = policy.choose(state), policy.choose(state)
    assert first.action == second.action and first.q_values == second.q_values
    assert policy.manifest["selected_on"].startswith("validation")


def test_the_shipped_policy_manifest_matches_its_weights() -> None:
    manifest_path = POLICY_DIR / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("the dialogue policy is not present")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256((POLICY_DIR / "policy.json").read_bytes()).hexdigest()
    assert digest == manifest["files"]["policy.json"]
