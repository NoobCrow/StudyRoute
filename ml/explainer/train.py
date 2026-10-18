"""Fine-tune the small student (FLAN-T5-small, Apache-2.0) on the verified rewrites, on your GPU.

    ml/.venv/Scripts/python ml/explainer/train.py --epochs 6

The student reads `rewrite the draft to answer the question | question: ... | flags: ... | draft: ...`
(the same compact input the runtime builds) and writes a reply that answers the question and keeps the
engine's figures. Its training targets are the teacher's VERIFIED rewrites plus the engine's own draft,
so it learns to answer directly and also learns that copying the draft is always safe.

Splits are by scenario, and the test set's wording is never seen in training. Writes a checkpoint and a
training log to ml/explainer/runs/. Synthetic data only.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "explainer" / "data"
RUNS = ROOT / "ml" / "explainer" / "runs"
BASE = "google/flan-t5-small"
MAX_SOURCE = 512
MAX_TARGET = 200


def source_text(question: str, draft: str) -> str:
    """Must equal app.ai.explainer.prompt.compact_input for a prompt with no policy flags."""
    return f"rewrite the draft to answer the question | question: {question[:300]} | flags: none | draft: {draft[:2000]}"


def load(split: str, draft_share: float, rng: random.Random) -> list[tuple[str, str]]:
    examples: list[tuple[str, str]] = []
    with open(DATA / f"verified_{split}.jsonl", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            source = source_text(row["question"], row["draft"])
            for rewrite in row["rewrites"]:
                examples.append((source, rewrite))
            # the engine's own draft is always a safe answer: keep a share of them as copy examples
            if rng.random() < draft_share or not row["rewrites"]:
                examples.append((source, row["draft"]))
    return examples


def batches(examples: list[tuple[str, str]], size: int, rng: random.Random):
    order = list(range(len(examples)))
    rng.shuffle(order)
    # bucket by length inside windows so padding stays small
    for start in range(0, len(order), size * 20):
        window = sorted(
            order[start : start + size * 20], key=lambda i: len(examples[i][0])
        )
        chunks = [window[k : k + size] for k in range(0, len(window), size)]
        rng.shuffle(chunks)
        for chunk in chunks:
            yield [examples[i] for i in chunk]


def evaluate(model, tokenizer, examples, device, size=64) -> float:
    model.eval()
    total, count = 0.0, 0
    with torch.no_grad():
        for batch in batches(examples, size, random.Random(0)):
            enc = tokenizer(
                [s for s, _ in batch],
                max_length=MAX_SOURCE,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).to(device)
            lab = tokenizer(
                [t for _, t in batch],
                max_length=MAX_TARGET,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).input_ids.to(device)
            lab[lab == tokenizer.pad_token_id] = -100
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(**enc, labels=lab).loss
            total += loss.item() * len(batch)
            count += len(batch)
    return total / max(count, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--draft-share", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--name", default="explainer-v1")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = "cuda"
    train = load("train", args.draft_share, rng)
    val = load("val", 0.25, random.Random(1))
    print(
        f"{len(train)} training examples, {len(val)} validation examples on {torch.cuda.get_device_name(0)}",
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    model = T5ForConditionalGeneration.from_pretrained(args.base).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps_per_epoch = math.ceil(len(train) / args.batch)
    total_steps = steps_per_epoch * args.epochs
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min(1.0, (s + 1) / 200) * max(0.05, 1 - s / total_steps)
    )

    best, log = float("inf"), []
    out = RUNS / args.name
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    step = 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running, seen = 0.0, 0
        for batch in batches(train, args.batch, rng):
            enc = tokenizer(
                [s for s, _ in batch],
                max_length=MAX_SOURCE,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).to(device)
            lab = tokenizer(
                [t for _, t in batch],
                max_length=MAX_TARGET,
                truncation=True,
                padding=True,
                return_tensors="pt",
            ).input_ids.to(device)
            lab[lab == tokenizer.pad_token_id] = -100
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = model(**enc, labels=lab).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            running += loss.item() * len(batch)
            seen += len(batch)
            step += 1
        val_loss = evaluate(model, tokenizer, val, device)
        entry = {
            "epoch": epoch,
            "train_loss": round(running / seen, 4),
            "val_loss": round(val_loss, 4),
            "minutes": round((time.time() - started) / 60, 1),
        }
        log.append(entry)
        print(entry, flush=True)
        if val_loss < best:
            best = val_loss
            model.save_pretrained(out / "best")
            tokenizer.save_pretrained(out / "best")
    (out / "log.json").write_text(
        json.dumps(
            {
                "base": args.base,
                "args": vars(args),
                "examples": len(train),
                "log": log,
                "best_val_loss": round(best, 4),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"best validation loss {best:.4f}; checkpoint in {out / 'best'}")


if __name__ == "__main__":
    main()
