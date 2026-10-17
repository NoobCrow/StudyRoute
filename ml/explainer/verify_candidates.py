"""Keep only the teacher's rewrites that pass the faithfulness checks.

    cd backend && .venv/Scripts/python ../ml/explainer/verify_candidates.py --split train

Reads `candidates_<split>.jsonl` (written by teach.py) and writes `verified_<split>.jsonl`, with the
rewrites that `app.ai.explainer.verify.check_rewrite` accepts, plus `teach_<split>.json`: how many
proposals there were, how many passed, and why the others failed. That failure rate is the reason the
check exists: a general language model, left alone, changes figures and drops disclaimers.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.explainer.verify import check_rewrite  # noqa: E402

DATA = ROOT / "ml" / "explainer" / "data"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("train", "val", "test"), required=True)
    args = parser.parse_args()

    reasons: Counter[str] = Counter()
    proposed = kept = pairs_with_rewrite = 0
    total = 0
    with (
        open(DATA / f"candidates_{args.split}.jsonl", encoding="utf-8") as source,
        open(
            DATA / f"verified_{args.split}.jsonl", "w", encoding="utf-8", newline="\n"
        ) as sink,
    ):
        for line in source:
            row = json.loads(line)
            total += 1
            good: list[str] = []
            for text in row.pop("candidates"):
                proposed += 1
                verdict = check_rewrite(row["draft"], text)
                if verdict.ok and text != row["draft"] and text not in good:
                    good.append(text)
                    kept += 1
                elif not verdict.ok:
                    reasons[verdict.reason] += 1
            pairs_with_rewrite += bool(good)
            sink.write(json.dumps({**row, "rewrites": good}, ensure_ascii=False) + "\n")
    summary = {
        "split": args.split,
        "pairs": total,
        "proposed": proposed,
        "verified": kept,
        "verified_share": round(kept / max(proposed, 1), 4),
        "pairs_with_a_verified_rewrite": pairs_with_rewrite,
        "rejected_for": dict(reasons.most_common()),
    }
    (DATA / f"teach_{args.split}.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
