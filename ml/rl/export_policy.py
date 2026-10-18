"""Export the best trained dialogue policy as plain JSON the API can run with NumPy.

    ml/.venv/Scripts/python ml/rl/export_policy.py --names dm1 dm2 dm3

Picks the run with the best VALIDATION return (never a test result), writes
backend/app/ai/dialogue/model/policy.json and a manifest with the SHA-256 of the weights, the
training settings and the hash of the simulator's observation bank.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ml" / "rl"), str(ROOT / "backend")]

import torch  # noqa: E402
from app.ai.dialogue.state import ACTIONS, FEATURES  # noqa: E402
from env import BANK  # noqa: E402
from train_dqn import build_net  # noqa: E402

OUT = ROOT / "backend" / "app" / "ai" / "dialogue" / "model"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--names", nargs="+", default=["dm1", "dm2", "dm3"])
    parser.add_argument("--policy-id", default="studyroute-dm-v1")
    args = parser.parse_args()
    runs = {}
    for name in args.names:
        config = json.loads((ROOT / "ml" / "runs" / "rl" / name / "config.json").read_text("utf-8"))
        runs[name] = config
    best = max(runs, key=lambda n: runs[n]["best_val_return"])
    print({n: round(c["best_val_return"], 4) for n, c in runs.items()}, "-> best", best)
    net = build_net()
    net.load_state_dict(
        torch.load(ROOT / "ml" / "runs" / "rl" / best / "best.pt", map_location="cpu")
    )
    layers = []
    for module in net:
        if isinstance(module, torch.nn.Linear):
            layers.append(
                {"w": module.weight.detach().t().tolist(), "b": module.bias.detach().tolist()}
            )
    OUT.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"layers": layers}, separators=(",", ":"))
    (OUT / "policy.json").write_text(body, encoding="utf-8", newline="\n")
    digest = hashlib.sha256((OUT / "policy.json").read_bytes()).hexdigest()
    config = runs[best]
    manifest = {
        "policy_id": args.policy_id,
        "created": date.today().isoformat(),
        "files": {"policy.json": digest},
        "algorithm": "Double DQN with action masking, trained against a simulated parent",
        "network": f"{FEATURES} -> 64 -> 64 -> {len(ACTIONS)} (ReLU)",
        "actions": [a.name for a in ACTIONS],
        "selected_run": best,
        "selected_on": "validation return (test goals were never used)",
        "training": {
            k: config[k]
            for k in (
                "args",
                "rewards",
                "best_val_return",
                "gpu",
                "torch",
                "train_seconds",
                "transitions",
            )
        },
        "observation_bank_sha256": hashlib.sha256(BANK.read_bytes()).hexdigest(),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print("wrote", OUT, "policy sha256", digest[:12])


if __name__ == "__main__":
    main()
