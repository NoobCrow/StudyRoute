"""Turn the IBM synthetic AML transactions into the review-priority model's training table.

    ml/.venv/Scripts/python ml/aml/fetch.py     # once: checks the download and records its hash
    ml/.venv/Scripts/python ml/aml/build.py

Reads `HI-Small_Trans.csv` (about 5 million synthetic transactions, a few thousand of them labelled
as laundering by the generator), counts every sender's and receiver's earlier payments, and builds
the model's input with the very function the app uses (`app.ai.risk.features.vectorise`). The data
is split by TIME, not at random: the first 60% of the period trains, the next 20% tunes and the
last 20% is the test, because a bank scores tomorrow's payments with what it learned yesterday.
Synthetic data only; nothing here is a real person or account.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ai.risk.features import (
    FACT_NAMES,
    FEATURE_NAMES,
    LONG_GAP_HOURS,
    quantile_table,
    vectorise,
)
from history import hours_since_previous, prior_in_window

DATA = ROOT / "ml" / "aml" / "data"
COLUMNS = [
    "ts", "from_bank", "from_account", "to_bank", "to_account",
    "amount_received", "currency_received", "amount_paid", "currency_paid",
    "format", "laundering",
]  # fmt: skip
DAY, WEEK = 86_400, 7 * 86_400
SPLITS = {"train": 0, "val": 1, "test": 2}


def read() -> pd.DataFrame:
    frame = pd.read_csv(
        DATA / "external" / "HI-Small_Trans.csv", header=0, names=COLUMNS
    )
    frame["ts"] = pd.to_datetime(frame["ts"], format="%Y/%m/%d %H:%M")
    return frame


def facts_of(frame: pd.DataFrame) -> tuple[dict[str, np.ndarray], np.ndarray]:
    t = (frame["ts"] - frame["ts"].min()).dt.total_seconds().to_numpy(dtype=np.int64)
    sender = pd.factorize(frame["from_bank"].astype(str) + "|" + frame["from_account"])[
        0
    ]
    receiver = pd.factorize(frame["to_bank"].astype(str) + "|" + frame["to_account"])[
        0
    ]  # for pairs
    pair = pd.factorize(sender.astype(np.int64) * (receiver.max() + 1) + receiver)[0]
    facts = {
        "amount": frame["amount_paid"].to_numpy(dtype=np.float64),
        "currency": frame["currency_paid"].to_numpy(dtype=object),
        "sender_24h": prior_in_window(sender, t, DAY),
        "sender_7d": prior_in_window(sender, t, WEEK),
        "sender_total": prior_in_window(sender, t, None),
        "pair_count": prior_in_window(pair, t, None),
        "hours_since_last": hours_since_previous(sender, t, LONG_GAP_HOURS),
    }
    assert set(facts) == set(FACT_NAMES)
    return facts, t


def channel_counts(frame: pd.DataFrame) -> dict[str, dict[str, float]]:
    """How many laundering labels each payment channel holds. Kept as a record, not as an input."""
    out: dict[str, dict[str, float]] = {}
    groups = frame.groupby("format")["laundering"].agg(["size", "sum"])
    for name, row in groups.iterrows():
        out[str(name)] = {
            "rows": int(row["size"]),
            "laundering": int(row["sum"]),
            "share": round(float(row["sum"] / row["size"]), 6),
        }
    cross = frame["currency_paid"] != frame["currency_received"]
    out["(cross-currency, any channel)"] = {
        "rows": int(cross.sum()),
        "laundering": int(frame.loc[cross, "laundering"].sum()),
        "share": round(float(frame.loc[cross, "laundering"].mean()), 6),
    }
    return out


def main() -> None:
    frame = read()
    channels = channel_counts(frame)
    print(
        f"{len(frame):,} transactions, {int(frame['laundering'].sum()):,} labelled laundering"
    )
    facts, t = facts_of(frame)
    cut_train, cut_val = np.quantile(t, [0.6, 0.8])
    split = np.where(t <= cut_train, 0, np.where(t <= cut_val, 1, 2)).astype(np.int8)
    train = split == 0
    tables = {
        name: quantile_table(facts["amount"][train & (facts["currency"] == name)])
        for name in sorted(set(facts["currency"]))
        if (train & (facts["currency"] == name)).sum() >= 50
    }
    x = vectorise(facts, tables).astype(np.float32)
    mean = x[train].mean(axis=0)
    std = x[train].std(axis=0) + 1e-6
    y = frame["laundering"].to_numpy(dtype=np.int8)
    np.savez_compressed(DATA / "table.npz", x=x, y=y, split=split, t=t)
    meta = {
        "features": list(FEATURE_NAMES),
        "mean": [float(v) for v in mean],
        "std": [float(v) for v in std],
        "quantiles": tables,
        "rows": {k: int((split == i).sum()) for k, i in SPLITS.items()},
        "positives": {k: int(y[split == i].sum()) for k, i in SPLITS.items()},
        "period_days": round(float(t.max()) / DAY, 1),
        "channels": channels,
    }
    (DATA / "table_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    print(
        json.dumps({k: meta[k] for k in ("rows", "positives", "period_days")}, indent=1)
    )


if __name__ == "__main__":
    main()
