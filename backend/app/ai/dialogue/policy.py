"""Run the trained dialogue policy: a small multilayer network in plain NumPy.

The weights are data (JSON), checked against a manifest's SHA-256 before use. The network only
ranks the actions that ``state.legal_actions`` allows, so even a corrupted or badly trained file
cannot make the assistant run a plan with a missing amount or skip a conflict. If the file is
missing or fails its check, ``load_policy`` returns None and the assistant uses its fixed
behaviour (run as soon as the amount is known).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.dialogue.state import ACTIONS, FEATURES, Action, DialogueState, features, legal_actions

logger = logging.getLogger("studyroute.ai")
POLICY_DIR = Path(__file__).resolve().parent / "model"


@dataclass(frozen=True)
class Choice:
    action: Action
    q_values: dict[str, float]  # the network's score for every legal action
    policy_id: str
    sha256: str


class DialoguePolicy:
    def __init__(self, directory: Path = POLICY_DIR) -> None:
        import numpy as np

        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        path = directory / "policy.json"
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"]["policy.json"]:
            raise ValueError("policy.json does not match its recorded SHA-256")
        body = json.loads(path.read_text(encoding="utf-8"))
        self._layers = [
            (np.asarray(layer["w"], dtype="float64"), np.asarray(layer["b"], dtype="float64"))
            for layer in body["layers"]
        ]
        if self._layers[0][0].shape[0] != FEATURES or self._layers[-1][0].shape[1] != len(ACTIONS):
            raise ValueError("policy.json does not fit the current state and actions")
        self.manifest: dict[str, Any] = manifest
        self.policy_id: str = manifest["policy_id"]
        self.sha256: str = manifest["files"]["policy.json"]

    def scores(self, state: DialogueState) -> list[float]:
        import numpy as np

        x = np.asarray(features(state), dtype="float64")
        for index, (weights, bias) in enumerate(self._layers):
            x = x @ weights + bias
            if index < len(self._layers) - 1:
                x = np.maximum(x, 0.0)
        return [float(v) for v in x]

    def choose(self, state: DialogueState) -> Choice:
        legal = legal_actions(state)
        scores = self.scores(state)
        best = max((a for a in ACTIONS if legal[a]), key=lambda a: scores[a])
        shown = {a.name: round(scores[a], 3) for a in ACTIONS if legal[a]}
        return Choice(best, shown, self.policy_id, self.sha256)


def load_policy(mode: str = "auto", directory: Path = POLICY_DIR) -> DialoguePolicy | None:
    """The policy, or None when switched off, absent or failing its integrity check."""
    if mode == "off":
        return None
    try:
        return DialoguePolicy(directory)
    except (ImportError, OSError, KeyError, ValueError) as exc:
        logger.warning(
            "dialogue policy not used (%s); the assistant runs plans as soon as it can", exc
        )
        return None


def reviewed_action(state: DialogueState, proposed: Action) -> Action:
    """Runtime safety envelope, not a learned improvement or transaction authorization.

    Do not silently drop a missing deadline at the model's turn limit. A user may explicitly
    choose no deadline. Every complete plan gets a read-back, even if the model wants RUN.
    Conflict clarification takes priority; turn budgets never authorize skipping review.
    """
    if not state.amount.present or state.amount.conflict:
        return Action.ASK_AMOUNT
    if state.task == "CADENCE":
        if not state.months.present or state.months.conflict:
            return Action.ASK_MONTHS
    elif state.date.conflict or (not state.date.present and not state.date_skipped):
        return Action.ASK_DATE
    if not state.confirmed:
        return Action.CONFIRM
    return proposed
