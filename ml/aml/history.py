"""Count a sender's earlier payments for millions of rows at once (training side).

For row i, "earlier" means a row of the same key that comes before it in time (ties broken by row
order). The live scorer answers the same question with a database query; the test
``backend/tests/test_risk_history.py`` checks that both give the same numbers.
"""

from __future__ import annotations

import numpy as np

BIG = (
    1 << 34
)  # larger than any time value in seconds, so key * BIG + time sorts by key, then time


def _order(key: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    order = np.lexsort((np.arange(len(key)), t, key))
    return order, key[order].astype(np.int64), t[order].astype(np.int64)


def _unsort(order: np.ndarray, values: np.ndarray) -> np.ndarray:
    out = np.empty_like(values)
    out[order] = values
    return out


def prior_in_window(key: np.ndarray, t: np.ndarray, window: int | None) -> np.ndarray:
    """How many earlier rows share the key and fall within `window` seconds (None = ever)."""
    order, k, ts = _order(key, t)
    position = np.arange(len(k))
    if window is None:
        left = np.searchsorted(k, k, side="left")
    else:
        composite = k * BIG + ts
        left = np.searchsorted(composite, k * BIG + (ts - window), side="left")
    return _unsort(order, position - left)


def hours_since_previous(key: np.ndarray, t: np.ndarray, fill: float) -> np.ndarray:
    """Hours since the previous row with the same key, or `fill` for the first one."""
    order, k, ts = _order(key, t)
    gap = np.full(len(k), fill, dtype=np.float64)
    same = k[1:] == k[:-1]
    gap[1:][same] = (ts[1:][same] - ts[:-1][same]) / 3600.0
    return _unsort(order, gap)
