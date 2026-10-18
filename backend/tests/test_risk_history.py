"""The two ways of counting earlier payments agree: the fast one used in training and a plain loop.

Training counts millions of rows with a sort and a search (``ml/aml/history.py``). The live app asks
the database the same question for one payment. If the fast way ever disagreed with the plain
meaning ("earlier rows of the same key within the window"), the model would be trained on numbers
it never sees in use. This test checks the fast way against a brute-force loop on random data.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ML = Path(__file__).resolve().parents[2] / "ml" / "aml"
if not (ML / "history.py").exists():  # pragma: no cover - a stripped checkout
    pytest.skip("the training code is not available", allow_module_level=True)
sys.path.insert(0, str(ML))

from history import hours_since_previous, prior_in_window  # noqa: E402

from app.ai.risk.features import FACT_NAMES, FEATURE_NAMES, FEATURES, vectorise  # noqa: E402


def brute_count(key: np.ndarray, t: np.ndarray, window: int | None) -> np.ndarray:
    out = np.zeros(len(key), dtype=np.int64)
    for i in range(len(key)):
        for j in range(len(key)):
            if key[j] != key[i] or (t[j], j) >= (t[i], i):
                continue
            if window is None or t[j] >= t[i] - window:
                out[i] += 1
    return out


def brute_gap(key: np.ndarray, t: np.ndarray, fill: float) -> np.ndarray:
    out = np.full(len(key), fill)
    for i in range(len(key)):
        earlier = [j for j in range(len(key)) if key[j] == key[i] and (t[j], j) < (t[i], i)]
        if earlier:
            previous = max(earlier, key=lambda j: (t[j], j))
            out[i] = (t[i] - t[previous]) / 3600.0
    return out


@pytest.fixture
def rows() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(7)
    key = rng.integers(0, 12, size=300)
    t = rng.integers(0, 10 * 86_400, size=300)
    t[1::7] = t[0::7]  # a few rows share the exact second of another row
    return key, t


@pytest.mark.parametrize("window", [3_600, 86_400, 7 * 86_400, None])
def test_prior_counts_match_a_plain_loop(
    rows: tuple[np.ndarray, np.ndarray], window: int | None
) -> None:
    key, t = rows
    assert np.array_equal(prior_in_window(key, t, window), brute_count(key, t, window))


def test_hours_since_the_previous_payment_match_a_plain_loop(
    rows: tuple[np.ndarray, np.ndarray],
) -> None:
    key, t = rows
    assert np.allclose(hours_since_previous(key, t, 720.0), brute_gap(key, t, 720.0))


def test_ties_count_the_row_that_comes_first_only() -> None:
    key = np.array([1, 1, 1])
    t = np.array([100, 100, 100])
    assert prior_in_window(key, t, 3_600).tolist() == [0, 1, 2]


# ---- the shared feature function ------------------------------------------------------------------------


def one(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "amount": np.array([2000.0]), "currency": np.array(["US Dollar"]),
        "sender_24h": np.array([2]), "sender_7d": np.array([5]), "sender_total": np.array([9]),
        "hours_since_last": np.array([12.0]), "pair_count": np.array([0]),
    }  # fmt: skip
    base.update(overrides)
    return base


TABLES = {"US Dollar": [float(v) for v in np.linspace(0, 10_000, 101)]}


def test_vectorise_gives_one_named_column_per_feature() -> None:
    assert set(one()) == set(FACT_NAMES)
    row = vectorise(one(), TABLES)
    assert row.shape == (1, FEATURES) == (1, len(FEATURE_NAMES))
    named = dict(zip(FEATURE_NAMES, row[0], strict=True))
    assert named["amount_percentile"] == pytest.approx(0.2)
    assert named["pair_new"] == 1 and named["sender_new"] == 0
    assert named["sender_total"] == pytest.approx(np.log1p(9))


def test_a_batch_and_a_single_row_give_the_same_numbers() -> None:
    batch = vectorise({k: np.concatenate([v, v]) for k, v in one().items()}, TABLES)
    assert np.allclose(batch[0], batch[1]) and np.allclose(batch[0], vectorise(one(), TABLES)[0])


def test_the_inputs_leave_out_the_channel_the_time_and_the_receivers_fan_in() -> None:
    """Found with ml/aml/ablate.py: each would teach the model a habit of the generator."""
    blob = " ".join(FEATURE_NAMES + FACT_NAMES)
    for word in (
        "format",
        "cross_currency",
        "same_bank",
        "hour_sin",
        "weekend",
        "receiver",
        "round",
    ):
        assert word not in blob, word


def test_an_unknown_currency_sits_in_the_middle() -> None:
    row = vectorise(one(currency=np.array(["Zlotych"])), TABLES)
    assert row[0][FEATURE_NAMES.index("amount_percentile")] == 0.5
