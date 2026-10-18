"""Small independent rerun; does not tune the model or overwrite the full evaluation."""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
import platform
import json
from pathlib import Path
import evaluate as E


def main():
    reader = E.load_reader("auto")
    if reader is None:
        raise SystemExit("Missing model/runtime")
    result = {}
    for name in ("blind", "hard", "natural"):
        data = E.load_split(name)
        result[name] = E.evaluate(data, lambda text: E.agent_system(reader, text))
    out = {"scope": "Frozen holdout reproduction; not new evidence of generalisation", "results": result,
           "generated_utc": datetime.now(timezone.utc).isoformat(),
           "python": platform.python_version(),
           "source_sha256": {str(f.relative_to(E.ROOT)): hashlib.sha256(f.read_bytes()).hexdigest()
                             for f in sorted((E.ROOT / "backend/app/ai").rglob("*.py"))},
           "dataset_sha256": {name: hashlib.sha256((E.ROOT / "ml/data/generated" / (name + ".jsonl.gz")).read_bytes()).hexdigest() for name in result},
           "evaluation_sha256": hashlib.sha256((E.ROOT / "ml/evaluate.py").read_bytes()).hexdigest(),
           "model_sha256": reader.sha256}
    path = E.ROOT / "submission/evidence/release/holdout-recheck.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print({k: {m: v[m] for m in ("routing_accuracy", "attack_blocked")} for k,v in result.items()})


if __name__ == "__main__":
    main()
