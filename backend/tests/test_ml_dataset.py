"""The training data and the model that was trained on it are consistent, and nothing leaks.

The data lives in ml/data/generated (built by ml/data/build_dataset.py). The test sets must never
share a message with the training data, and the shipped model must record the exact data it was
trained on.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from app.ai.nlu.runtime import MODEL_DIR
from app.ai.nlu.schema import INTENTS, SLOTS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "data" / "generated"
SPLITS = ("train", "val", "test", "dev", "test_heldout", "natural", "oos_public", "hard", "blind")

if not (DATA / "manifest.json").is_file():  # pragma: no cover - only in a stripped checkout
    pytest.skip("the dataset is not present", allow_module_level=True)


def load(name: str) -> list[dict]:
    with gzip.open(DATA / f"{name}.jsonl.gz", "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))


def test_every_split_matches_the_hash_in_the_manifest(manifest: dict) -> None:
    for name in SPLITS:
        digest = hashlib.sha256((DATA / f"{name}.jsonl.gz").read_bytes()).hexdigest()
        assert digest == manifest["splits"][name]["sha256"], name
        assert manifest["splits"][name]["examples"] == len(load(name)), name


def test_every_example_is_well_formed() -> None:
    for name in SPLITS:
        for example in load(name):
            text = example["text"]
            assert example["intent"] in INTENTS, (name, text)
            assert 1 <= len(text) <= 1000, (name, text)
            for start, end, label in example["spans"]:
                assert label in SLOTS and 0 <= start < end <= len(text), (name, text)
            assert "gold" in example


def test_no_message_is_in_both_the_training_data_and_a_test_set() -> None:
    seen = {e["text"].strip().lower() for name in ("train", "val") for e in load(name)}
    for name in ("test_heldout", "dev", "natural", "oos_public", "hard", "blind"):
        shared = [e["text"] for e in load(name) if e["text"].strip().lower() in seen]
        assert not shared, (name, shared[:3])


def test_the_hand_written_sets_are_never_in_the_training_data() -> None:
    train = {e["text"].strip().lower() for e in load("train")}
    for name in ("hard", "blind"):
        assert not [e for e in load(name) if e["text"].strip().lower() in train]


def test_the_held_out_templates_never_appear_in_training() -> None:
    families = {e["family"] for e in load("train") if e["family"].startswith(tuple(INTENTS))}
    held = {e["family"] for e in load("test_heldout")}
    assert held and not (held & families)


def test_the_shipped_model_records_the_data_it_was_trained_on(manifest: dict) -> None:
    model = json.loads((MODEL_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert model["dataset"]["version"] == manifest["version"]
    for name in ("train", "val", "dev"):
        assert model["dataset"]["splits"][name]["sha256"] == manifest["splits"][name]["sha256"], (
            f"the model was not trained on the current {name} data: retrain and export"
        )


def test_the_public_source_is_credited_with_its_licence(manifest: dict) -> None:
    source = manifest["sources"]["banking77"]
    assert source["license"] == "CC BY 4.0" and "Casanueva" in source["name"]
    third_party = (ROOT / "docs" / "THIRD_PARTY.md").read_text(encoding="utf-8")
    assert "Banking77" in third_party


def test_no_personal_data_is_in_the_data() -> None:
    import re

    email = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
    for name in SPLITS:
        for example in load(name):
            assert not email.search(example["text"]), (name, example["text"])
