"""A quality floor for the shipped review-priority model, so a worse one cannot be swapped in quietly.

The floors sit well below what `ml/aml/train.py` measured on the test period (the last fifth of the
timeline, never used for any choice). The full report is docs/AI_RISK.md. What this guards: the files
are the ones that were recorded, the recorded results are still good, the model ranks the obvious
cases the right way round, and it is fast.
"""

from __future__ import annotations

import time

import pytest

from app.ai.risk.scorer import MODEL_DIR, RiskScorer

if not (MODEL_DIR / "risk.json").exists():  # pragma: no cover - a stripped checkout
    pytest.skip("the shipped risk model is not available", allow_module_level=True)

scorer = RiskScorer()
RESULTS = scorer.manifest["results"]


def facts(
    amount: float,
    s24: int = 0,
    s7: int = 0,
    total: int = 0,
    hours: float = 720.0,
    pair: int = 0,
) -> dict[str, object]:
    return {
        "amount": amount,
        "currency": "US Dollar",
        "sender_24h": s24,
        "sender_7d": s7,
        "sender_total": total,
        "hours_since_last": hours,
        "pair_count": pair,
    }


def test_the_manifest_says_where_the_model_came_from() -> None:
    manifest = scorer.manifest
    assert manifest["data"]["licence"] == "CDLA-Sharing-1.0"
    assert "synthetic" in manifest["note"].lower()
    assert manifest["split"].startswith("by time")
    assert manifest["kind"] in ("mlp", "linear")


def test_the_recorded_test_results_are_still_good() -> None:
    shipped = RESULTS[scorer.manifest["kind"]]["test"]
    assert shipped["average_precision"] >= 0.30
    assert shipped["roc_auc"] >= 0.93
    assert shipped["found_in_top_1_percent"] >= 0.50
    assert shipped["found_in_top_5_percent"] >= 0.70


def test_it_beats_random_and_biggest_first_by_a_wide_margin() -> None:
    shipped = RESULTS[scorer.manifest["kind"]]["test"]["average_precision"]
    assert shipped >= 50 * RESULTS["random_order"]["test"]["average_precision"]
    assert shipped >= 50 * RESULTS["biggest_amounts_first"]["test"]["average_precision"]


def test_a_burst_of_payments_to_a_new_receiver_ranks_above_a_routine_instalment() -> None:
    burst = scorer.score(facts(9_900.12, s24=6, s7=8, total=20, hours=0.5, pair=0))
    routine = scorer.score(facts(2_031.55, s24=0, s7=0, total=5, hours=700.0, pair=5))
    assert burst.percentile > routine.percentile + 15
    assert burst.band in ("MEDIUM", "HIGH") and routine.band == "LOW"


def test_a_round_amount_is_not_read_as_the_safest_payment_possible() -> None:
    """An earlier version learned that from a handful of examples; anyone could have used it."""
    exact = scorer.score(facts(10_500.0, s24=5, s7=5, total=5, hours=0.01, pair=0))
    odd = scorer.score(facts(10_500.37, s24=5, s7=5, total=5, hours=0.01, pair=0))
    assert abs(exact.percentile - odd.percentile) <= 2 and exact.band == odd.band


def test_the_priority_is_a_percentile_and_a_band() -> None:
    for amount in (100.0, 5_000.0, 41_967.0, 1_000_000.0):
        priority = scorer.score(facts(amount))
        assert 0 <= priority.percentile <= 100
        assert priority.band in ("LOW", "MEDIUM", "HIGH")
        assert priority.model_id == scorer.model_id


def test_the_same_payment_always_gets_the_same_priority() -> None:
    first = scorer.score(facts(13_115.0, s24=1, total=3, hours=20.0))
    assert all(scorer.score(facts(13_115.0, s24=1, total=3, hours=20.0)) == first for _ in range(5))


def test_scoring_is_fast_enough_to_run_on_every_request() -> None:
    started = time.perf_counter()
    for _ in range(200):
        scorer.score(facts(13_115.0))
    assert (time.perf_counter() - started) / 200 < 0.02


def test_the_bands_mean_what_they_say_in_the_tuning_data() -> None:
    bands = scorer._bands  # the cut-offs and hit rates measured on the tuning period
    flagged = [bands[name]["flagged_share"] for name in ("HIGH", "MEDIUM", "LOW")]
    assert flagged[0] > flagged[1] > flagged[2]
    assert flagged[0] >= 0.30
    assert bands["HIGH"]["from_logit"] > bands["MEDIUM"]["from_logit"]


def test_a_new_receiver_after_a_run_of_payments_is_read_as_unusual_and_the_model_says_why() -> None:
    reading = scorer.score(facts(10_500.37, s24=5, s7=5, total=5, hours=0.01, pair=0))
    assert reading.band in ("MEDIUM", "HIGH")
    assert (
        "PERSON" in reading.drivers and len(reading.factors) == 4 and reading.population == "first"
    )
    assert reading.hit_rate is not None and reading.hit_rate > 0.01
