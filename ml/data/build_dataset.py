"""Build the training and evaluation data for the StudyRoute reader.

    python ml/data/build_dataset.py

Sources:
  1. Synthetic messages composed from templates (ml/data/templates.py), with typos, politeness,
     casing, code-switching and unlabelled distractor numbers.
  2. Banking77 (PolyAI, CC BY 4.0): real customer questions. Only the card, ATM and account
     questions that StudyRoute does not handle are used, as OUT_OF_SCOPE.
  3. A hand-written hard set (ml/data/hard_set.txt) used ONLY for testing, never for training or
     for choosing thresholds.

Splits: train / val / test (same templates), dev (templates never seen in training, used ONLY to
calibrate confidence and pick thresholds), test_heldout (a different set of unseen templates),
hard (hand-written), oos_public and natural (Banking77's own test split: out-of-scope
questions, and real questions mapped to StudyRoute intents).
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import random
import sys
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))

import generate  # noqa: E402
import templates  # noqa: E402
from markup import parse_markup  # noqa: E402

from app.ai.nlu.schema import INTENTS, SLOTS  # noqa: E402
from app.ai.nlu.slots import Span, read_slots  # noqa: E402
from app.engine.money import CURRENCY_EXPONENTS  # noqa: E402

SEED = 20261015
OUT = HERE / "generated"
EXTERNAL = HERE / "external"
TODAY = generate.TODAY
BANKING77 = {
    "train": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/train.csv",
    "test": "https://raw.githubusercontent.com/PolyAI-LDN/task-specific-datasets/master/banking_data/test.csv",
}
# Card, ATM and app-admin questions: not StudyRoute's business. Transfers, exchange rates,
# identity checks and refunds are left out on purpose because they overlap StudyRoute's own topics.
OOS_CATEGORIES = frozenset(
    """activate_my_card age_limit apple_pay_or_google_pay atm_support automatic_top_up
    balance_not_updated_after_cheque_or_cash_deposit card_about_to_expire card_acceptance
    card_arrival card_delivery_estimate card_linking card_not_working card_swallowed
    cash_withdrawal_charge cash_withdrawal_not_recognised change_pin compromised_card
    contactless_not_working declined_card_payment declined_cash_withdrawal
    direct_debit_payment_not_recognised disposable_card_limits edit_personal_details
    get_disposable_virtual_card get_physical_card getting_spare_card getting_virtual_card
    lost_or_stolen_card lost_or_stolen_phone order_physical_card passcode_forgotten
    pending_card_payment pending_cash_withdrawal pending_top_up pin_blocked terminate_account
    top_up_by_card_charge top_up_by_cash_or_cheque top_up_failed top_up_limits top_up_reverted
    topping_up_by_card transaction_charged_twice virtual_card_not_working visa_or_mastercard
    wrong_amount_of_cash_received""".split()
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_banking77() -> dict[str, Path]:
    EXTERNAL.mkdir(exist_ok=True)
    paths = {}
    for split, url in BANKING77.items():
        path = EXTERNAL / f"banking77_{split}.csv"
        if not path.exists():
            print(f"downloading {url}")
            with urllib.request.urlopen(url, timeout=60) as reply:  # noqa: S310 (fixed https URL)
                path.write_bytes(reply.read())
        paths[split] = path
    return paths


# Real customer questions that ARE about what StudyRoute does (cost of an exchange, fees on a
# transfer, how long it takes, where it is, identity checks), mapped to StudyRoute's own intents.
B77_INTENTS = {
    "exchange_rate": "COMPARE", "exchange_charge": "CHARGES", "transfer_fee_charged": "CHARGES",
    "extra_charge_on_statement": "CHARGES", "transfer_timing": "DEADLINE",
    "pending_transfer": "STATUS", "transfer_not_received_by_recipient": "STATUS",
    "failed_transfer": "STATUS", "declined_transfer": "STATUS",
    "balance_not_updated_after_bank_transfer": "STATUS", "verify_my_identity": "KYC",
    "why_verify_identity": "KYC", "unable_to_verify_identity": "KYC",
    "verify_source_of_funds": "CHECKLIST", "country_support": "HELP",
    "supported_cards_and_currencies": "HELP", "fiat_currency_support": "HELP",
}  # fmt: skip


def banking77_rows(path: Path, seed: int) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    random.Random(seed).shuffle(rows)
    return rows


def _example(row: dict[str, str], intent: str) -> dict[str, object]:
    return {"text": row["text"].strip(), "intent": intent, "spans": [], "family": "banking77"}


def banking77_oos(rows: list[dict[str, str]], start: int, stop: int) -> list[dict[str, object]]:
    pool = [r for r in rows if r["category"] in OOS_CATEGORIES]
    return [_example(r, "OUT_OF_SCOPE") for r in pool[start:stop]]


def banking77_mapped(
    rows: list[dict[str, str]], start: int, stop: int
) -> list[dict[str, object]]:
    """Per category, the rows from index ``start`` to ``stop``."""
    out = []
    for category, intent in B77_INTENTS.items():
        pool = [r for r in rows if r["category"] == category]
        out += [_example(r, intent) for r in pool[start:stop]]
    return out


def read_hard_set(path: Path) -> list[dict[str, object]]:
    examples = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        group, intent, marked = (part.strip() for part in line.split("|", 2))
        if intent not in INTENTS:
            raise ValueError(f"{path.name}:{number}: unknown intent {intent}")
        text, spans = parse_markup(marked)
        examples.append(
            {
                "text": text, "intent": intent, "spans": [list(s) for s in spans],
                "family": f"hard:{group}", "group": group,
            }
        )  # fmt: skip
    return examples


def validate(example: dict[str, object]) -> dict[str, object] | None:
    """Attach the gold values read by the deterministic code; drop what it cannot read."""
    text = str(example["text"])
    spans = [Span(label, s, e, text[s:e]) for s, e, label in example["spans"]]  # type: ignore[misc]
    for span in spans:
        if span.label not in SLOTS:
            raise ValueError(f"unknown label {span.label} in {text!r}")
    values = read_slots(spans, TODAY, CURRENCY_EXPONENTS)
    if values.problems:
        return None
    return {**example, "gold": values.as_dict()}


def dedupe(examples: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    unique = []
    for example in examples:
        key = str(example["text"]).strip().lower()
        if key not in seen:
            seen.add(key)
            unique.append(example)
    return unique


def write(name: str, examples: list[dict[str, object]]) -> Path:
    path = OUT / f"{name}.jsonl.gz"
    lines = "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in examples) + "\n"
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(lines.encode("utf-8"))
    return path


def counts(examples: list[dict[str, object]]) -> dict[str, object]:
    labels = Counter(span[2] for e in examples for span in e["spans"])  # type: ignore[attr-defined]
    return {
        "examples": len(examples),
        "intents": dict(sorted(Counter(str(e["intent"]) for e in examples).items())),
        "span_labels": dict(sorted(labels.items())),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    synthetic: list[dict[str, object]] = []
    dropped = 0
    for intent, volume in templates.VOLUME.items():
        synthetic += generate.generate_intent(intent, volume, SEED)
    synthetic += generate.generate_intent("OUT_OF_SCOPE", 3200, SEED)
    checked = []
    for example in synthetic:
        valid = validate(example)
        if valid is None:
            dropped += 1
        else:
            checked.append(valid)
    checked = dedupe(checked)

    heldout = [e for e in checked if e["role"] == "heldout"]
    dev = [e for e in checked if e["role"] == "dev"]
    seen_templates = [e for e in checked if e["role"] == "seen"]
    rng.shuffle(seen_templates)
    paths = fetch_banking77()
    train_rows = banking77_rows(paths["train"], SEED)
    test_rows = banking77_rows(paths["test"], SEED + 1)
    b_train = banking77_oos(train_rows, 0, 3300)
    b_test = banking77_oos(test_rows, 0, 700)
    mapped_train = banking77_mapped(train_rows, 0, 110)
    mapped_val = banking77_mapped(train_rows, 110, 135)
    natural_test = banking77_mapped(test_rows, 0, 40)
    train_texts = {str(e["text"]).lower() for e in seen_templates}
    heldout = [e for e in heldout if str(e["text"]).lower() not in train_texts]
    dev = [e for e in dev if str(e["text"]).lower() not in train_texts]

    n = len(seen_templates)
    cut_val, cut_test = int(n * 0.90), int(n * 0.95)
    # Banking77's own test split repeats a few of its training messages: keep every test set clean.
    seen_in_training = train_texts | {str(e["text"]).strip().lower() for e in mapped_train + mapped_val + b_train}
    b_test = [e for e in b_test if str(e["text"]).strip().lower() not in seen_in_training]
    natural_test = [e for e in natural_test if str(e["text"]).strip().lower() not in seen_in_training]
    splits = {
        "train": seen_templates[:cut_val]
        + [validate(e) for e in b_train[:3000] + mapped_train],  # type: ignore[misc]
        "val": seen_templates[cut_val:cut_test]
        + [validate(e) for e in b_train[3000:] + mapped_val],  # type: ignore[misc]
        "test": seen_templates[cut_test:],
        "dev": dev,
        "test_heldout": heldout,
        "oos_public": [validate(e) for e in b_test],  # type: ignore[misc]
        "natural": [validate(e) for e in natural_test],  # type: ignore[misc]
        "hard": [v for e in read_hard_set(HERE / "hard_set.txt") if (v := validate(e))],
        "blind": [v for e in read_hard_set(HERE / "blind_set.txt") if (v := validate(e))],
    }
    manifest: dict[str, object] = {
        "version": "studyroute-nlu-data-v1",
        "seed": SEED,
        "today_anchor": TODAY.isoformat(),
        "built": date.today().isoformat(),
        "synthetic_examples_dropped_by_normalizer": dropped,
        "sources": {
            "synthetic": "ml/data/templates.py, render.py, generate.py (original work)",
            "hard_set": "ml/data/hard_set.txt (hand-written by the project, test only; used for error analysis during development, so a diagnostic, not a clean test)",
            "blind_set": "ml/data/blind_set.txt (hand-written after the model was frozen, evaluated once)",
            "banking77": {
                "name": "Banking77 (Casanueva et al., 2020, PolyAI)",
                "license": "CC BY 4.0",
                "urls": BANKING77,
                "sha256": {k: sha256(p) for k, p in paths.items()},
                "used_as": "OUT_OF_SCOPE (card, ATM and app-admin questions) and, mapped by "
                "category, real questions about fees, timing, status and identity checks",
                "category_to_intent": B77_INTENTS,
            },
        },
        "splits": {},
    }
    for name, examples in splits.items():
        examples = [e for e in examples if e]
        path = write(name, examples)
        manifest["splits"][name] = {**counts(examples), "sha256": sha256(path)}  # type: ignore[index]
        print(f"{name:13} {len(examples):6} examples")
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("dropped by the normalizer:", dropped)


if __name__ == "__main__":
    main()
