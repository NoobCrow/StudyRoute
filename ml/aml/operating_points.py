"""Accuracy, precision and recall of the shipped review-priority model, at the points a bank could pick.

    ml/.venv/Scripts/python ml/aml/operating_points.py

A ranking model has no single accuracy: it has a trade-off. Choose how many payments to send to a
person (a threshold) and precision (how many of those were flagged in the data) and recall (how many
of the flagged ones were caught) move against each other. This script prints the whole trade-off on
the TEST period, with the threshold chosen on the TUNING period only (best F1), for all payments and
for first payments to a receiver, and writes `submission/evidence/ai_risk_operating_points.json`.

It exists because "accuracy" alone is meaningless here: only about 0.1% of the transactions are
flagged, so answering "not flagged" every time is 99.9% accurate and catches nothing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.risk.features import FEATURE_NAMES

DATA = ROOT / "ml" / "aml" / "data"
MODEL = ROOT / "backend" / "app" / "ai" / "risk" / "model" / "risk.json"
PAIR_NEW = FEATURE_NAMES.index("pair_new")


def logits(x: np.ndarray, body: dict) -> np.ndarray:
    z = (x - np.asarray(body["mean"], dtype=np.float32)) / np.asarray(
        body["std"], dtype=np.float32
    )
    layers = [
        (
            np.asarray(layer["w"], dtype=np.float32),
            np.asarray(layer["b"], dtype=np.float32),
        )
        for layer in body["layers"]
    ]
    for index, (w, b) in enumerate(layers):
        z = z @ w + b
        if index < len(layers) - 1:
            z = np.maximum(z, 0.0)
    return z[:, 0]


def confusion(y: np.ndarray, flagged: np.ndarray) -> dict[str, float]:
    tp = int((flagged & (y == 1)).sum())
    fp = int((flagged & (y == 0)).sum())
    fn = int((~flagged & (y == 1)).sum())
    tn = int((~flagged & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "sent_to_a_person": tp + fp,
        "true_positives": tp,
        "false_positives": fp,
        "missed": fn,
        "accuracy": round((tp + tn) / len(y), 5),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def best_f1_threshold(y: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(-s, kind="stable")
    ys = y[order]
    tp = np.cumsum(ys)
    k = np.arange(1, len(ys) + 1)
    precision, recall = tp / k, tp / max(ys.sum(), 1)
    f1 = np.where(
        precision + recall > 0, 2 * precision * recall / (precision + recall + 1e-12), 0
    )
    return float(s[order][int(np.argmax(f1))])


def main() -> None:
    table = np.load(DATA / "table.npz")
    body = json.loads(MODEL.read_text(encoding="utf-8"))
    x, y, split = table["x"], table["y"], table["split"]
    out: dict[str, dict] = {}
    for label, only_new in (
        ("all payments", False),
        ("first payments to a receiver", True),
    ):
        masks = {name: split == code for name, code in (("tuning", 1), ("test", 2))}
        if only_new:
            masks = {k: m & (x[:, PAIR_NEW] == 1) for k, m in masks.items()}
        s = {k: logits(x[m], body) for k, m in masks.items()}
        ys = {k: y[m] for k, m in masks.items()}
        threshold = best_f1_threshold(ys["tuning"], s["tuning"])
        rows = {
            "threshold_chosen_on_tuning_period": round(threshold, 4),
            "test_rows": int(masks["test"].sum()),
            "test_flagged": int(ys["test"].sum()),
            "best_f1_point": confusion(ys["test"], s["test"] >= threshold),
            "top_share_of_payments": {},
            "never_flag_anything": confusion(
                ys["test"], np.zeros(len(ys["test"]), dtype=bool)
            ),
        }
        order = np.argsort(-s["test"], kind="stable")
        for share in (0.001, 0.005, 0.01, 0.02, 0.05, 0.1):
            top = np.zeros(len(order), dtype=bool)
            top[order[: max(1, int(len(order) * share))]] = True
            rows["top_share_of_payments"][f"{share:.1%}"] = confusion(ys["test"], top)
        out[label] = rows
    # The routing the review desk actually uses: the bands' cut-offs were set on the tuning period
    # (HIGH = its top 0.1% of payments, MEDIUM = the next 0.4%); a person looks at MEDIUM and HIGH.
    test = split == 2
    s_test = logits(x[test], body)
    high, medium = (
        body["bands"]["HIGH"]["from_logit"],
        body["bands"]["MEDIUM"]["from_logit"],
    )
    routed = {
        "medium or high (a person looks)": confusion(y[test], s_test >= medium),
        "high only": confusion(y[test], s_test >= high),
        "medium only": confusion(y[test], (s_test >= medium) & (s_test < high)),
    }
    first = x[test][:, PAIR_NEW] == 1
    routed["medium or high, first payments to a receiver only"] = confusion(
        y[test][first], (s_test >= medium)[first]
    )
    out["routing used by the review desk"] = routed
    path = ROOT / "submission" / "evidence" / "ai_risk_operating_points.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
