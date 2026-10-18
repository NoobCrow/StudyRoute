"""How far can an honest model go? Try richer household-history inputs and a tree model.

    ml/.venv/Scripts/python ml/aml/explore.py

Rules of this experiment, so the result can be trusted:

* Every number printed here is on the TUNING period. The test period is not read at all. The final
  model is chosen from these numbers and only then measured once on the test period
  (`train_final.py`).
* Every extra input is something the sandbox could compute from its own payment table for one
  household: how many new receivers it paid lately, how soon it paid this same receiver again, how this
  amount compares with its previous one. Nothing about other households, the payment channel, the
  currencies or the time of day.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "backend"))

from app.ai.risk.features import FEATURE_NAMES, LONG_GAP_HOURS
from build import DAY, WEEK, read
from history import BIG, hours_since_previous, prior_in_window

DATA = HERE / "data"


def average_precision(y: np.ndarray, s: np.ndarray) -> float:
    order = np.argsort(-s, kind="stable")
    ys = y[order].astype(np.float64)
    precision = np.cumsum(ys) / np.arange(1, len(ys) + 1)
    return float((precision * ys).sum() / max(ys.sum(), 1.0))


def recall_at(y: np.ndarray, s: np.ndarray, share: float) -> float:
    top = np.argsort(-s, kind="stable")[: max(1, int(len(s) * share))]
    return float(y[top].sum() / max(y.sum(), 1))


def count_prior_marked(
    key: np.ndarray, t: np.ndarray, mark: np.ndarray, window: int
) -> np.ndarray:
    """How many marked rows of the same key came strictly earlier, within `window` seconds."""
    composite = np.sort(key[mark].astype(np.int64) * BIG + t[mark])
    k = key.astype(np.int64)
    upper = np.searchsorted(composite, k * BIG + t, side="left")
    lower = np.searchsorted(composite, k * BIG + (t - window), side="left")
    return upper - lower


def previous_amount_ratio(
    key: np.ndarray, t: np.ndarray, amount: np.ndarray, currency: np.ndarray
):
    """log(amount / the key's previous amount) when both are in the same currency, else 0."""
    order = np.lexsort((np.arange(len(key)), t, key))
    k, a, c = key[order], amount[order], currency[order]
    out = np.zeros(len(key))
    same = (k[1:] == k[:-1]) & (c[1:] == c[:-1]) & (a[:-1] > 0) & (a[1:] > 0)
    out[1:][same] = np.log(a[1:][same] / a[:-1][same])
    result = np.empty_like(out)
    result[order] = out
    return result


def extras(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    t = (frame["ts"] - frame["ts"].min()).dt.total_seconds().to_numpy(dtype=np.int64)
    sender = pd.factorize(frame["from_bank"].astype(str) + "|" + frame["from_account"])[
        0
    ]
    receiver = pd.factorize(frame["to_bank"].astype(str) + "|" + frame["to_account"])[0]
    pair = pd.factorize(sender.astype(np.int64) * (receiver.max() + 1) + receiver)[0]
    new_pair = prior_in_window(pair, t, None) == 0
    amount = frame["amount_paid"].to_numpy(dtype=np.float64)
    currency = frame["currency_paid"].to_numpy(dtype=object)
    return {
        "same_receiver_24h": np.log1p(prior_in_window(pair, t, DAY)),
        "new_receivers_7d": np.log1p(count_prior_marked(sender, t, new_pair, WEEK)),
        "new_receivers_24h": np.log1p(count_prior_marked(sender, t, new_pair, DAY)),
        "hours_since_same_receiver": np.log1p(
            hours_since_previous(pair, t, LONG_GAP_HOURS)
        ),
        "amount_vs_previous": previous_amount_ratio(sender, t, amount, currency),
    }


def fit(name, x, y, split, params, rounds=1500) -> dict:
    started = time.time()
    tr, va = split == 0, split == 1
    dtrain = xgb.DMatrix(x[tr], label=y[tr])
    dval = xgb.DMatrix(x[va], label=y[va])
    booster = xgb.train(
        {"objective": "binary:logistic", "eval_metric": "aucpr", "device": "cuda",
         "tree_method": "hist", "seed": 2026, **params},
        dtrain, rounds, evals=[(dval, "tuning")], early_stopping_rounds=100, verbose_eval=False,
    )  # fmt: skip
    scores = booster.predict(dval, iteration_range=(0, booster.best_iteration + 1))
    out = {
        "name": name,
        "params": params,
        "trees": booster.best_iteration + 1,
        "tuning_average_precision": round(average_precision(y[va], scores), 4),
        "tuning_found_in_top_0.5_percent": round(recall_at(y[va], scores, 0.005), 4),
        "tuning_found_in_top_1_percent": round(recall_at(y[va], scores, 0.01), 4),
        "tuning_found_in_top_5_percent": round(recall_at(y[va], scores, 0.05), 4),
        "seconds": round(time.time() - started),
    }
    print(json.dumps(out), flush=True)
    return out


def main() -> None:
    table = np.load(DATA / "table.npz")
    x8, y, split = table["x"], table["y"], table["split"]
    frame = read()
    more = extras(frame)
    names = [*FEATURE_NAMES, *more]
    x14 = np.column_stack([x8, *[more[k] for k in more]]).astype(np.float32)
    print(f"{len(names)} inputs: {names[len(FEATURE_NAMES) :]}", flush=True)

    results = []
    base = {"max_depth": 6, "eta": 0.05, "subsample": 0.8, "colsample_bytree": 0.8,
            "min_child_weight": 5, "scale_pos_weight": 20}  # fmt: skip
    results.append(fit("trees on the current 8 inputs", x8, y, split, base))
    results.append(fit("trees on 8 + 5 household-history inputs", x14, y, split, base))
    for depth in (4, 8, 10):
        results.append(
            fit(f"8+5, depth {depth}", x14, y, split, {**base, "max_depth": depth})
        )
    for weight in (1, 5, 50):
        results.append(
            fit(
                f"8+5, positive weight {weight}",
                x14,
                y,
                split,
                {**base, "scale_pos_weight": weight},
            )
        )
    (DATA / "explore.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
