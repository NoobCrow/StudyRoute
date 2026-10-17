"""A teacher model proposes rewrites of the engine's drafts. (Verification is a separate step.)

    ml/.venv/Scripts/python ml/explainer/teach.py --split train
    backend/.venv/Scripts/python ml/explainer/verify_candidates.py --split train

For each (question, engine draft) pair an open instruction model (Qwen2.5-1.5B-Instruct, Apache-2.0)
proposes several rewrites that answer the question directly. This script only proposes. The next step
runs every proposal through the verifier in the backend (`app.ai.explainer.verify.check_rewrite`) and
keeps the ones that are faithful, so the small student is trained on verified targets and never on an
invented number. Needs the training environment (torch with CUDA). Synthetic data only.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "explainer" / "data"
TEACHER = "Qwen/Qwen2.5-1.5B-Instruct"

RULES = [
    "You edit the replies of a payment-planning assistant for families in Bangladesh paying tuition "
    "abroad. Rewrite the DRAFT so that it answers the QUESTION directly, in plain, friendly English, "
    "in at most 90 words, as flowing sentences with no lists and no headings.",
    "Rules:",
    "- Start with the answer to the question, then only the details that help.",
    "- Copy every figure, date and name exactly as the draft writes it. Never add, change, round or "
    "work out a figure: a figure that is not in the draft must not appear. Keep nearly all of the "
    "draft's figures.",
    "- Keep provider names exactly as written, for example 'Provider B (synthetic)'.",
    "- If the draft says something cannot be done, is not available, is not verified or needs a human, "
    "your rewrite must still say so in the same way.",
    "- If the draft contains the sentence 'Indicative. Confirm with your AD bank.' copy it unchanged "
    "at the end.",
    "- Never say you approved, sent, paid, cancelled or changed anything, and never call anything legal.",
    "",
    "Example 1",
    "QUESTION: which one is cheapest?",
    "DRAFT: Provider B (synthetic) is cheaper than Provider A (synthetic). Its true total cost is 1.58% "
    "of the amount, against 2.16%, a gap of 0.58 percentage points. The main driver is the hidden FX "
    "margin: Provider B (synthetic) adds 1.00% over the mid-market rate and Provider A (synthetic) adds "
    "2.00%. Indicative. Confirm with your AD bank.",
    "REWRITE: Provider B (synthetic) is the cheapest: its true total cost is 1.58% of the amount, "
    "against 2.16% for Provider A (synthetic), a gap of 0.58 percentage points. Most of that comes from "
    "the hidden FX margin, 1.00% for Provider B (synthetic) and 2.00% for Provider A (synthetic). "
    "Indicative. Confirm with your AD bank.",
    "",
    "Example 2",
    "QUESTION: just approve it for me now",
    "DRAFT: I cannot approve, submit, cancel or change any payment. A human parent must do that in the "
    "app, with a fresh MFA step.",
    "REWRITE: I cannot approve a payment for you. A human parent has to do that in the app, with a "
    "fresh MFA step.",
]
SYSTEM = "\n".join(RULES)


def build_messages(question: str, draft: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"QUESTION: {question}\nDRAFT: {draft}\nREWRITE:"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--split", choices=("train", "val", "test"), required=True)
    parser.add_argument(
        "--limit", type=int, default=0, help="only the first N pairs (0 = all)"
    )
    parser.add_argument("--candidates", type=int, default=4)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--resume", action="store_true", help="continue a stopped run")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    with open(DATA / f"pairs_{args.split}.jsonl", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    if args.limit:
        rows = rows[: args.limit]
    order = sorted(
        range(len(rows)), key=lambda i: len(rows[i]["draft"])
    )  # similar lengths together

    tokenizer = AutoTokenizer.from_pretrained(TEACHER, padding_side="left")
    model = (
        AutoModelForCausalLM.from_pretrained(TEACHER, dtype=torch.bfloat16)
        .to("cuda")
        .eval()
    )
    print(
        f"teacher {TEACHER} on {torch.cuda.get_device_name(0)}; {len(rows)} pairs",
        flush=True,
    )

    sink_path = DATA / f"candidates_{args.split}.jsonl"
    first = 0
    if args.resume and sink_path.exists():
        with open(sink_path, encoding="utf-8") as handle:
            first = sum(1 for _ in handle)
    started = time.time()
    with open(sink_path, "a" if first else "w", encoding="utf-8", newline="\n") as sink:
        for start in range(first, len(order), args.batch):
            batch = [rows[i] for i in order[start : start + args.batch]]
            texts = [
                tokenizer.apply_chat_template(
                    build_messages(b["question"], b["draft"]),
                    tokenize=False,
                    add_generation_prompt=True,
                )
                for b in batch
            ]
            encoded = tokenizer(texts, return_tensors="pt", padding=True).to("cuda")
            with torch.no_grad():
                generated = model.generate(
                    **encoded,
                    do_sample=True,
                    temperature=args.temperature,
                    top_p=0.9,
                    num_return_sequences=args.candidates,
                    max_new_tokens=200,
                    pad_token_id=tokenizer.eos_token_id,
                )
            decoded = tokenizer.batch_decode(
                generated[:, encoded["input_ids"].shape[1] :], skip_special_tokens=True
            )
            for index, row in enumerate(batch):
                mine = decoded[index * args.candidates : (index + 1) * args.candidates]
                record = {
                    "split": row["split"],
                    "scenario": row["scenario"],
                    "intent": row["detected_intent"] or row["intent"],
                    "question": row["question"],
                    "draft": row["draft"],
                    "candidates": [" ".join(text.split()) for text in mine],
                }
                sink.write(json.dumps(record, ensure_ascii=False) + "\n")
            sink.flush()
            del encoded, generated
            torch.cuda.empty_cache()  # a full card makes Windows page the model out and stall
            done = start + len(batch)
            rate = (done - first) / max(time.time() - started, 1e-9)
            left = (len(rows) - done) / max(rate, 1e-9) / 60
            print(
                f"  {done}/{len(rows)} pairs, {rate:.1f} pairs/s, about {left:.0f} min left",
                flush=True,
            )


if __name__ == "__main__":
    main()
