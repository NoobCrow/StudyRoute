"""Try every kind of model on the same data and the same time split, and record all of it.

    ml/.venv/Scripts/python ml/aml/compare.py

Models: rule baselines, logistic regression, three sizes of neural network, gradient-boosted trees
(XGBoost and LightGBM), random forest, extra trees, naive Bayes and an isolation forest (which never
sees a label). Each one is tried on two sets of inputs: the 8 shipped inputs, and those 8 plus 5 more
household-history inputs (new receivers lately, how soon the same receiver was paid again, how this
amount compares with the last one).

How the numbers are kept honest:

* Every model is trained on the first 60% of the timeline only. Its settings (tree depth, class
  weight, epochs) are chosen on the TUNING period (the next 20%) by average precision.
* The cut-offs and the best-F1 threshold are set on the tuning period, then applied unchanged to the
  TEST period (the last 20%). The table lists both periods for every model.
* Which model to ship is decided from the tuning column. The test column is the report. If a person
  picks a model because its test number is highest, the test number is no longer an unbiased estimate;
  the differences between close models (a few points of average precision on 1,797 flagged payments)
  are within the noise anyway.

Output: submission/evidence/ai_risk_model_comparison.json (and a table printed at the end).
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "backend"))

import lightgbm as lgb
import torch
import xgboost as xgb
from app.ai.risk.features import FEATURE_NAMES
from build import read
from explore import extras
from sklearn.ensemble import (
    ExtraTreesClassifier,
    IsolationForest,
    RandomForestClassifier,
)
from sklearn.naive_bayes import GaussianNB
from torch import nn

DATA = HERE / "data"
EVIDENCE = HERE.parents[1] / "submission" / "evidence"
PAIR_NEW = FEATURE_NAMES.index("pair_new")
AMOUNT = FEATURE_NAMES.index("amount_percentile")
N8 = len(FEATURE_NAMES)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


# ---- data ---------------------------------------------------------------------------------------


def load() -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    path = DATA / "table13.npz"
    if not path.exists():
        base = np.load(DATA / "table.npz")
        more = extras(read())
        names = [*FEATURE_NAMES, *more]
        x = np.column_stack([base["x"], *more.values()]).astype(np.float32)
        np.savez_compressed(
            path, x=x, y=base["y"], split=base["split"], names=np.array(names)
        )
    table = np.load(path)
    return table["x"], table["y"], table["split"], [str(n) for n in table["names"]]


# ---- metrics ------------------------------------------------------------------------------------


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(-s, kind="stable")
    ys = y[order].astype(np.float64)
    return float(
        (np.cumsum(ys) / np.arange(1, len(ys) + 1) * ys).sum() / max(ys.sum(), 1.0)
    )


def roc_auc(y: np.ndarray, s: np.ndarray) -> float:
    ranks = np.empty(len(s))
    ranks[np.argsort(s, kind="stable")] = np.arange(1, len(s) + 1)
    p = int(y.sum())
    return float((ranks[y == 1].sum() - p * (p + 1) / 2) / (p * (len(y) - p)))


def found_in_top(y: np.ndarray, s: np.ndarray, share: float) -> float:
    top = np.argsort(-s, kind="stable")[: max(1, int(len(s) * share))]
    return float(y[top].sum() / max(y.sum(), 1))


def confusion(y: np.ndarray, flagged: np.ndarray) -> dict[str, float]:
    tp = int((flagged & (y == 1)).sum())
    fp = int((flagged & (y == 0)).sum())
    fn = int((~flagged & (y == 1)).sum())
    tn = int((~flagged & (y == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "sent": tp + fp,
        "accuracy": round((tp + tn) / len(y), 5),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def best_f1_threshold(y: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(-s, kind="stable")
    ys = y[order]
    tp = np.cumsum(ys)
    precision = tp / np.arange(1, len(ys) + 1)
    recall = tp / max(ys.sum(), 1)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    return float(s[order][int(np.argmax(f1))])


def report(s_val, s_test, y_val, y_test, first_test) -> dict[str, Any]:
    high, medium = np.quantile(s_val, 0.999), np.quantile(s_val, 0.995)
    threshold = best_f1_threshold(y_val, s_val)
    return {
        "tuning": {
            "average_precision": round(average_precision(y_val, s_val), 4),
            "roc_auc": round(roc_auc(y_val, s_val), 4),
            "found_in_top_1_percent": round(found_in_top(y_val, s_val, 0.01), 4),
            "found_in_top_5_percent": round(found_in_top(y_val, s_val, 0.05), 4),
        },
        "test": {
            "average_precision": round(average_precision(y_test, s_test), 4),
            "roc_auc": round(roc_auc(y_test, s_test), 4),
            "found_in_top_1_percent": round(found_in_top(y_test, s_test, 0.01), 4),
            "found_in_top_5_percent": round(found_in_top(y_test, s_test, 0.05), 4),
            "medium_or_high": confusion(y_test, s_test >= medium),
            "high_only": confusion(y_test, s_test >= high),
            "best_f1_point": confusion(y_test, s_test >= threshold),
            "first_payments_average_precision": round(
                average_precision(y_test[first_test], s_test[first_test]), 4
            ),
            "first_payments_best_f1_point": confusion(
                y_test[first_test], (s_test >= threshold)[first_test]
            ),
        },
    }


# ---- the models ---------------------------------------------------------------------------------


def standardise(x: np.ndarray, train: np.ndarray) -> np.ndarray:
    mean, std = x[train].mean(axis=0), x[train].std(axis=0) + 1e-6
    return np.clip((x - mean) / std, -8.0, 8.0).astype(np.float32)


def torch_scores(
    x, y, split, hidden: list[int], epochs: int, pos_weight: float
) -> np.ndarray:
    torch.manual_seed(2026)
    z = torch.as_tensor(standardise(x, split == 0), device=DEVICE)
    target = torch.as_tensor(y[split == 0], dtype=torch.float32, device=DEVICE)
    train_x = z[torch.as_tensor(split == 0, device=DEVICE)]
    sizes = [x.shape[1], *hidden, 1]
    layers: list[nn.Module] = []
    for i in range(len(sizes) - 1):
        layers.append(nn.Linear(sizes[i], sizes[i + 1]))
        if i < len(sizes) - 2:
            layers.append(nn.ReLU())
    model = nn.Sequential(*layers).to(DEVICE)
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight, device=DEVICE))
    val = split == 1

    def score_all() -> np.ndarray:
        model.eval()
        with torch.no_grad():
            return (
                torch.cat(
                    [
                        model(z[i : i + 262_144]).squeeze(1)
                        for i in range(0, len(z), 262_144)
                    ]
                )
                .cpu()
                .numpy()
            )

    best, best_scores = -1.0, None
    for _ in range(epochs):
        model.train()
        order = torch.randperm(len(train_x), device=DEVICE)
        for start in range(0, len(order), 16_384):
            idx = order[start : start + 16_384]
            optimiser.zero_grad()
            loss_fn(model(train_x[idx]).squeeze(1), target[idx]).backward()
            optimiser.step()
        scores = score_all()
        tuning = average_precision(
            y[val], scores[val]
        )  # the tuning period picks the epoch
        if tuning > best:
            best, best_scores = tuning, scores
    return best_scores


def logistic(x, y, split):
    return torch_scores(x, y, split, [], 12, 20.0)


def mlp(hidden: list[int]):
    return lambda x, y, split: torch_scores(x, y, split, hidden, 12, 20.0)


def xgboost_scores(x, y, split) -> np.ndarray:
    tr, va = split == 0, split == 1
    dtrain, dval = xgb.DMatrix(x[tr], label=y[tr]), xgb.DMatrix(x[va], label=y[va])
    best, best_scores = -1.0, None
    for depth in (4, 6, 8):
        for weight in (1, 5, 20):
            booster = xgb.train(
                {"objective": "binary:logistic", "eval_metric": "aucpr", "device": "cuda",
                 "tree_method": "hist", "seed": 2026, "max_depth": depth, "eta": 0.05,
                 "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5,
                 "scale_pos_weight": weight},
                dtrain, 1500, evals=[(dval, "t")], early_stopping_rounds=100, verbose_eval=False,
            )  # fmt: skip
            rounds = (0, booster.best_iteration + 1)
            scores = booster.predict(xgb.DMatrix(x), iteration_range=rounds)
            tuning = average_precision(y[va], scores[va])
            if tuning > best:
                best, best_scores = tuning, scores
    return best_scores


def lightgbm_scores(x, y, split) -> np.ndarray:
    tr, va = split == 0, split == 1
    best, best_scores = -1.0, None
    for leaves in (15, 31, 63):
        for weight in (1, 5):
            model = lgb.LGBMClassifier(
                n_estimators=1500, learning_rate=0.05, num_leaves=leaves, subsample=0.8,
                subsample_freq=1, colsample_bytree=0.8, min_child_samples=20,
                scale_pos_weight=weight, random_state=2026, verbose=-1, n_jobs=16,
            )  # fmt: skip
            model.fit(
                x[tr], y[tr], eval_set=[(x[va], y[va])], eval_metric="average_precision",
                callbacks=[lgb.early_stopping(100, verbose=False)],
            )  # fmt: skip
            scores = model.predict_proba(x)[:, 1]
            tuning = average_precision(y[va], scores[va])
            if tuning > best:
                best, best_scores = tuning, scores
    return best_scores


def downsampled(x, y, split, keep: float = 0.1) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(2026)
    train = np.flatnonzero(split == 0)
    keep_rows = train[(y[train] == 1) | (rng.random(len(train)) < keep)]
    return x[keep_rows], y[keep_rows]


def forest(kind) -> Callable:
    def run(x, y, split):
        xs, ys = downsampled(x, y, split)
        model = kind(n_estimators=300, min_samples_leaf=3, n_jobs=16, random_state=2026,
                     class_weight="balanced_subsample")  # fmt: skip
        model.fit(xs, ys)
        return model.predict_proba(x)[:, 1]

    return run


def naive_bayes(x, y, split) -> np.ndarray:
    model = GaussianNB().fit(x[split == 0], y[split == 0])
    return model.predict_log_proba(x)[:, 1]


def isolation(x, y, split) -> np.ndarray:
    rng = np.random.default_rng(2026)
    train = np.flatnonzero(split == 0)
    sample = rng.choice(train, size=min(500_000, len(train)), replace=False)
    model = IsolationForest(
        n_estimators=300, max_samples=65_536, random_state=2026, n_jobs=16
    )
    model.fit(x[sample])  # no labels at all
    return -model.score_samples(x)


MODELS: list[tuple[str, str, Callable, tuple[str, ...]]] = [
    # (name, kind, function, input sets it is tried on)
    ("logistic regression", "linear", logistic, ("8", "13")),
    ("neural network 8-64-32", "neural network", mlp([64, 32]), ("8", "13")),
    (
        "neural network 128-64 (shipped shape)",
        "neural network",
        mlp([128, 64]),
        ("8", "13"),
    ),
    ("neural network 256-128-64", "neural network", mlp([256, 128, 64]), ("8", "13")),
    ("XGBoost (gradient-boosted trees)", "trees", xgboost_scores, ("8", "13")),
    ("LightGBM (gradient-boosted trees)", "trees", lightgbm_scores, ("8", "13")),
    ("random forest", "trees", forest(RandomForestClassifier), ("8", "13")),
    ("extra trees", "trees", forest(ExtraTreesClassifier), ("8", "13")),
    ("naive Bayes", "probabilistic", naive_bayes, ("8", "13")),
    ("isolation forest (no labels)", "unsupervised", isolation, ("8", "13")),
]


def main() -> None:
    x_all, y, split, names = load()
    val, test = split == 1, split == 2
    first_test = x_all[test][:, PAIR_NEW] == 1
    print(
        f"{len(y):,} payments, {int(y.sum()):,} flagged; inputs {len(names)}: {names}",
        flush=True,
    )

    rows: list[dict[str, Any]] = []

    def add(name, kind, inputs, scores, seconds):
        rows.append({"model": name, "kind": kind, "inputs": inputs, "seconds": round(seconds),
                     **report(scores[val], scores[test], y[val], y[test], first_test)})  # fmt: skip
        r = rows[-1]
        print(f"{name:40s} {inputs:>3s} inputs  tuning AP {r['tuning']['average_precision']:.3f}"
              f"  test AP {r['test']['average_precision']:.3f}  ({seconds:.0f}s)", flush=True)  # fmt: skip

    # rule baselines: what a person would write without learning anything
    add("rule: biggest amount first", "rule", "8", x_all[:, AMOUNT], 0.0)
    add(
        "rule: a new receiver",
        "rule",
        "8",
        x_all[:, PAIR_NEW] + 1e-3 * x_all[:, AMOUNT],
        0.0,
    )
    add(
        "rule: new receiver, then amount",
        "rule",
        "8",
        1000 * x_all[:, PAIR_NEW] + x_all[:, AMOUNT],
        0.0,
    )
    rng = np.random.default_rng(2026)
    add("random order", "rule", "8", rng.random(len(y)), 0.0)

    for name, kind, function, sets in MODELS:
        for inputs in sets:
            x = x_all[:, :N8] if inputs == "8" else x_all
            started = time.time()
            try:
                scores = function(x, y, split)
            except (
                Exception
            ) as error:  # a model that cannot run is reported, not hidden
                print(f"{name} on {inputs} inputs FAILED: {error}", flush=True)
                continue
            add(name, kind, inputs, scores, time.time() - started)

    rows.sort(key=lambda r: -r["tuning"]["average_precision"])
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "ai_risk_model_comparison.json").write_text(
        json.dumps({"inputs": names, "models": rows}, indent=2), encoding="utf-8"
    )
    print("\nbest on the TUNING period:", rows[0]["model"], rows[0]["inputs"], "inputs")


if __name__ == "__main__":
    main()
