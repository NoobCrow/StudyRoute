"""Collect the backbone comparison (every run's dev-split result) into one evidence file.

    ml/.venv/Scripts/python ml/collect_ablation.py

Each ml/runs/<name>/config.json is written by ml/train.py. The dev split holds templates the
model never trained on, so it is the split used to choose the backbone; no test set is used.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAMES = {"minilm": "MiniLM-L12-H384", "allmini": "all-MiniLM-L12-v2", "e5": "e5-small-v2",
         "gte": "gte-small", "bge_lr5": "bge-small-en-v1.5 (lr 5e-5)", "bge": "bge-small-en-v1.5"}  # fmt: skip


def main() -> None:
    rows = []
    for name, label in NAMES.items():
        path = ROOT / "ml" / "runs" / name / "config.json"
        if not path.is_file():
            continue
        config = json.loads(path.read_text(encoding="utf-8"))
        rows.append({"run": name, "backbone": config["backbone"], "label": label,
                     "learning_rate": config["args"]["lr"], "epochs": config["args"]["epochs"],
                     "train_seconds": config["train_seconds"], "gpu": config["gpu"],
                     "dev_intent_accuracy": round(config["dev"]["intent_acc"], 4),
                     "dev_span_f1": round(config["dev"]["span_f1"], 4)})  # fmt: skip
    out = ROOT / "submission" / "evidence" / "ai_backbone_ablation.json"
    out.write_text(json.dumps({"selected": "bge", "split": "dev", "runs": rows}, indent=2) + "\n",
                   encoding="utf-8")  # fmt: skip
    for row in rows:
        print(f"{row['label']:32} lr {row['learning_rate']:<6} dev intent {row['dev_intent_accuracy']:.4f}  span F1 {row['dev_span_f1']:.4f}")


if __name__ == "__main__":
    main()
