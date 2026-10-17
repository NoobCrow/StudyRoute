"""The baseline the trained student must beat: the same small model, not trained.

    ml/.venv/Scripts/python ml/explainer/baseline_zero_shot.py --split test --limit 700

FLAN-T5-small is given exactly the input the trained student gets and asked, in the same words, to
rewrite the engine's draft. No training, no examples. Its outputs are written to
`baseline_zero_shot_<split>.jsonl` and scored by `evaluate.py` with the same checks as the student.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "explainer" / "data"


def source_text(question: str, draft: str) -> str:
    """The same input the runtime builds (app.ai.explainer.prompt.compact_input, no policy flags)."""
    return (
        f"rewrite the draft to answer the question | question: {question[:300]}"
        f" | flags: none | draft: {draft[:2000]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", default="test")
    parser.add_argument("--limit", type=int, default=700)
    args = parser.parse_args()

    with open(DATA / f"verified_{args.split}.jsonl", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle][: args.limit]
    tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-small")
    model = (
        T5ForConditionalGeneration.from_pretrained("google/flan-t5-small").cuda().eval()
    )
    with open(
        DATA / f"baseline_zero_shot_{args.split}.jsonl",
        "w",
        encoding="utf-8",
        newline="\n",
    ) as sink:
        for start in range(0, len(rows), 32):
            batch = rows[start : start + 32]
            encoded = tokenizer(
                [source_text(r["question"], r["draft"]) for r in batch],
                max_length=512,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).to("cuda")
            with torch.no_grad():
                out = model.generate(
                    **encoded, max_new_tokens=200, do_sample=False, num_beams=1
                )
            for row, ids in zip(batch, out, strict=True):
                text = tokenizer.decode(ids, skip_special_tokens=True)
                finished = tokenizer.eos_token_id in ids.tolist()
                sink.write(
                    json.dumps(
                        {
                            "question": row["question"],
                            "draft": row["draft"],
                            "output": text,
                            "finished": finished,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    print(f"wrote {len(rows)} zero-shot outputs")


if __name__ == "__main__":
    main()
