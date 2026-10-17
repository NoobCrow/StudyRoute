"""The numbers the review-priority model looks at, built the same way in training and in the app.

``vectorise`` is the one place where raw facts about a payment (its size and how often this
household paid before) become the model's input. Training calls it on millions of rows at once and
the live scorer calls it on one payment, so the two can never drift apart. Counting the earlier
payments is different work in each place (a sort and a search in training, a database query in the
app); ``tests/test_risk_history.py`` checks that the two ways of counting agree.

What is deliberately NOT here, and why (found with ``ml/aml/ablate.py``):

* The payment channel and the currencies. In the public data set no wire transfer and no
  cross-currency transfer is labelled as laundering, so a model that saw them would learn that every
  StudyRoute payment (a cross-currency wire) is harmless. That is the generator's habit.
* Whether the amount is a round number. Almost no payment in the data is round, so the network
  learned an extreme rule from a handful of examples (a round amount scored as the safest payment
  possible, which anyone could use). The amount enters only as a percentile within its currency.
* The time of day. It carries no meaning in the app.
* How many payments a receiver got from anyone. A university legitimately receives many.

Every fact here is something the sandbox knows about a payment. None is a name, an account number
or anything that identifies a person.
"""

from __future__ import annotations

from typing import Any

import numpy as np

QUANTILE_POINTS = 101
LONG_GAP_HOURS = 720.0  # no earlier payment: treated as a month of quiet

FEATURE_NAMES = (
    "amount_percentile",
    "sender_24h",
    "sender_7d",
    "sender_total",
    "hours_since_last",
    "sender_new",
    "pair_count",
    "pair_new",
)
FEATURES = len(FEATURE_NAMES)

# What `vectorise` needs, one array per name (all the same length).
FACT_NAMES = (
    "amount",  # in the currency it was paid in, whole units
    "currency",  # the dataset's name for it, e.g. "US Dollar"
    "sender_24h",  # the sender's earlier payments in the last 24 hours
    "sender_7d",
    "sender_total",
    "hours_since_last",  # since the sender's previous payment (LONG_GAP_HOURS if none)
    "pair_count",  # earlier payments from this sender to this receiver
)


def quantile_table(amounts: np.ndarray) -> list[float]:
    """101 points of an amount distribution (min, 1st percentile ... max)."""
    return [float(v) for v in np.quantile(amounts, np.linspace(0.0, 1.0, QUANTILE_POINTS))]


def _percentile(amount: np.ndarray, currency: np.ndarray, tables: dict[str, list[float]]) -> Any:
    out = np.full(amount.shape, 0.5, dtype=np.float64)  # a currency the table lacks: the middle
    grid = np.linspace(0.0, 1.0, QUANTILE_POINTS)
    for name, table in tables.items():
        mask = currency == name
        if mask.any():
            out[mask] = np.interp(amount[mask], np.asarray(table, dtype=np.float64), grid)
    return out


def vectorise(facts: dict[str, Any], tables: dict[str, list[float]]) -> Any:
    """Raw facts in, one row of FEATURES numbers per payment out (not yet standardised)."""
    amount = np.asarray(facts["amount"], dtype=np.float64)
    currency = np.asarray(facts["currency"])
    sender_total = np.asarray(facts["sender_total"], dtype=np.float64)
    pair_count = np.asarray(facts["pair_count"], dtype=np.float64)
    columns = [
        _percentile(amount, currency, tables),
        np.log1p(np.asarray(facts["sender_24h"], dtype=np.float64)),
        np.log1p(np.asarray(facts["sender_7d"], dtype=np.float64)),
        np.log1p(sender_total),
        np.log1p(np.asarray(facts["hours_since_last"], dtype=np.float64)),
        (sender_total == 0).astype(np.float64),
        np.log1p(pair_count),
        (pair_count == 0).astype(np.float64),
    ]
    matrix = np.stack(columns, axis=1)
    if matrix.shape[1] != FEATURES:
        raise AssertionError("FEATURE_NAMES and vectorise disagree")
    return matrix
