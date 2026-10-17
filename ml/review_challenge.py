"""Reproduce a small, frozen AI-authored challenge. NOT independent or blind evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import evaluate as E


def main():
    root = Path(__file__).resolve().parents[1]
    data = root / "ml/data/review_challenge_v2.jsonl"
    provenance = json.loads(data.with_suffix(".provenance.json").read_text())
    digest = hashlib.sha256(data.read_bytes()).hexdigest()
    if digest != provenance["dataset_sha256"]:
        raise SystemExit("Dataset differs from frozen provenance")
    rows = [json.loads(line) for line in data.read_text().splitlines() if line]
    reader = E.load_reader("auto")
    if reader is None:
        raise SystemExit("Trained reader unavailable")
    result = {
        "provenance": provenance,
        "generated_utc": datetime.now(UTC).isoformat(),
        "dataset_sha256": digest,
        "model_sha256": reader.sha256,
        "source_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((root / "backend/app/ai").rglob("*.py"))
        },
        "systems": {},
    }
    for name, system in {
        "rules": E.rules_system,
        "agent": lambda text: E.agent_system(reader, text),
    }.items():
        cases = []
        for row in rows:
            pred = system(row["text"])
            cases.append(
                {
                    **row,
                    "gold_route": E.route(row["intent"]),
                    "prediction": asdict(pred),
                    "correct": E.route(row["intent"]) == pred.intent,
                }
            )
        correct = sum(c["correct"] for c in cases)
        attacks = [c for c in cases if c["intent"] == "ATTACK"]
        result["systems"][name] = {
            "n": len(cases),
            "correct": correct,
            "routing_accuracy": correct / len(cases),
            "routing_ci95": E.wilson(correct, len(cases)),
            "attacks": len(attacks),
            "attacks_blocked": sum(
                c["prediction"]["intent"] == "ATTACK" for c in attacks
            ),
            "cases": cases,
        }
    out = root / "submission/evidence/v2/intent-challenge.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(
        {
            name: {k: v for k, v in data.items() if k != "cases"}
            for name, data in result["systems"].items()
        }
    )


if __name__ == "__main__":
    main()
