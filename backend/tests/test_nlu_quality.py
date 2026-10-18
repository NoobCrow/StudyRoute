"""A quality floor for the shipped reader, so a worse model cannot be swapped in quietly.

The floors sit a few points below what ml/evaluate.py measured, on data the model never trained on
(natural questions, held-out templates, out-of-scope questions). The full report is
docs/AI_EVALUATION.md; this test only guards against a regression.
"""

from __future__ import annotations

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from app.ai.nlu.runtime import MODEL_DIR, load_reader
from app.ai.nlu.slots import read_slots
from app.ai.nlu.understanding import understand
from app.ai.policy import check_text
from app.engine.money import CURRENCY_EXPONENTS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "data" / "generated"
TODAY = date(2026, 10, 15)
reader = load_reader("auto")

if reader is None or not DATA.is_dir():  # pragma: no cover - a stripped checkout
    pytest.skip("the trained reader or its test data is not available", allow_module_level=True)


def load(name: str, every: int = 1) -> list[dict]:
    with gzip.open(DATA / f"{name}.jsonl.gz", "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()][::every]


def route(name: str) -> str:
    return "HELP" if name in ("OUT_OF_SCOPE", "HELP") else name


def agent_route(text: str) -> str:
    got = understand(text, TODAY, CURRENCY_EXPONENTS, has_context=False, reader=reader)
    if got.attack or check_text(text).blocked:
        return "ATTACK"
    return "HELP" if got.out_of_scope else route(got.intent.value)


def accuracy(examples: list[dict]) -> float:
    right = sum(agent_route(e["text"]) == route(e["intent"]) for e in examples)
    return right / len(examples)


def test_real_customer_questions_are_routed_correctly() -> None:
    assert accuracy(load("natural")) >= 0.90


def test_wording_the_model_never_saw_is_routed_well() -> None:
    assert accuracy(load("test_heldout", every=8)) >= 0.85


def test_questions_outside_the_product_get_the_help_answer() -> None:
    assert accuracy(load("oos_public")) >= 0.97


def test_amounts_and_dates_are_read_correctly_in_unseen_wording() -> None:
    examples = [e for e in load("test_heldout", every=8) if e["gold"]["amount_minor"]]
    wrong = 0
    for example in examples:
        prediction = reader.predict(example["text"])
        values = read_slots(prediction.spans, TODAY, CURRENCY_EXPONENTS)
        gold = example["gold"]
        wrong += (values.amount_minor, values.currency) != (gold["amount_minor"], gold["currency"])
    assert wrong / len(examples) <= 0.02


def test_the_evaluation_report_describes_the_shipped_model() -> None:
    manifest = json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads(
        (ROOT / "submission" / "evidence" / "ai_evaluation.json").read_text("utf-8")
    )
    assert report["model"]["model_id"] == manifest["model_id"]
    assert report["model_sha256"] == manifest["files"]["model.onnx"], (
        "docs/AI_EVALUATION.md is stale: run ml/evaluate.py after exporting a model"
    )
