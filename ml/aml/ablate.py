"""What does the review-priority model actually learn from? Remove groups of inputs and measure again.

    ml/.venv/Scripts/python ml/aml/ablate.py [--device cpu]

The public data set is generated, and a generator leaves habits. This script finds them: it trains
the same small network with whole groups of inputs hidden (set to a constant), and reports the same
test-period numbers as `train.py`. The writing in `docs/AI_RISK.md` follows from this table. It also
counts how many laundering labels the data holds for each payment channel, because a model must not
be applied to a kind of payment the data never showed it (the counts come from `build.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import train

GROUPS = {
    "all eight inputs": [],
    "without the amount": ["amount_percentile"],
    "without the household's own history": [
        "sender_24h", "sender_7d", "sender_total", "hours_since_last", "sender_new",
    ],
    "without the receiver pair": ["pair_count", "pair_new"],
}  # fmt: skip
ONLY = {
    "only the amount": ["amount_percentile"],
    "only the household's own history": ["sender_", "hours_since_last"],
    "only the receiver pair": ["pair_"],
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--epochs", type=int, default=6)
    args = parser.parse_args()
    args.batch, args.pos_weight, args.rows = 16_384, 20.0, 0

    table = np.load(HERE / "data" / "table.npz")
    meta = json.loads((HERE / "data" / "table_meta.json").read_text(encoding="utf-8"))
    names = list(train.FEATURE_NAMES)
    x_all, y_all, split = table["x"], table["y"], table["split"]
    mean = np.asarray(meta["mean"], dtype=np.float32)
    std = np.asarray(meta["std"], dtype=np.float32)

    channels = meta["channels"]
    print(json.dumps(channels, indent=1))

    def run(hidden: list[int]) -> dict[str, float]:
        xs, ys = {}, {}
        for name, code in (("train", 0), ("val", 1), ("test", 2)):
            m = split == code
            part = ((x_all[m] - mean) / std).astype(np.float32)
            part[:, hidden] = 0.0
            xs[name] = torch.as_tensor(part, device=args.device)
            ys[name] = y_all[m]
        model, _, _ = train.fit("mlp", xs, ys, args)
        return train.report(ys["test"], train.scores(model, xs["test"]))

    results: dict[str, dict] = {}
    for label, group in GROUPS.items():
        results[label] = run([names.index(n) for n in group])
        print(label, results[label], flush=True)
    for label, prefixes in ONLY.items():
        keep = {
            i for i, n in enumerate(names) if any(n.startswith(p) for p in prefixes)
        }
        results[label] = run([i for i in range(len(names)) if i not in keep])
        print(label, results[label], flush=True)

    out = HERE.parents[1] / "submission" / "evidence" / "ai_risk_ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"channels": channels, "test_period": results}, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
