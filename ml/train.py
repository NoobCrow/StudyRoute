"""Fine-tune the StudyRoute reader on the GPU.

    ml/.venv/Scripts/python ml/train.py --backbone microsoft/MiniLM-L12-H384-uncased --name l12

One model reads a message and does two jobs at once: it picks the intent from the first token
and tags each word as outside or inside a slot (BIO). Training data comes from
ml/data/generated (build it with ml/data/build_dataset.py). The hand-written hard set and the
held-out templates are never touched here.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import torch
from huggingface_hub import hf_hub_download
from torch import nn

from common import IGNORE, ROOT, build_model, encode_example, load_split
from app.ai.nlu.schema import INTENTS, TAGS
from app.ai.nlu.tokenizer import WordPiece


def collate(items, pad_id: int, device: torch.device):
    longest = max(len(i.ids) for i in items)
    ids = torch.full((len(items), longest), pad_id, dtype=torch.long)
    mask = torch.zeros((len(items), longest), dtype=torch.long)
    labels = torch.full((len(items), longest), IGNORE, dtype=torch.long)
    for row, item in enumerate(items):
        n = len(item.ids)
        ids[row, :n] = torch.tensor(item.ids)
        mask[row, :n] = 1
        labels[row, :n] = torch.tensor(item.labels)
    intents = torch.tensor([i.intent for i in items], dtype=torch.long)
    return ids.to(device), mask.to(device), intents.to(device), labels.to(device)


def spans_from_tags(tag_ids: list[int]) -> set[tuple[int, int, str]]:
    """Entity spans (first word, last word, slot) from a BIO sequence of word tags."""
    found: set[tuple[int, int, str]] = set()
    start, label = None, None
    for index, tag_id in enumerate([*tag_ids, 0]):
        tag = TAGS[tag_id]
        if start is not None and not (tag.startswith("I-") and tag[2:] == label):
            found.add((start, index - 1, label or ""))
            start, label = None, None
        if tag.startswith(("B-", "I-")) and start is None:
            start, label = index, tag[2:]
    return found


@torch.no_grad()
def evaluate(model, items, pad_id, device, batch_size=256) -> dict[str, float]:
    model.eval()
    correct = total = 0
    tp = fp = fn = 0
    for offset in range(0, len(items), batch_size):
        batch = items[offset : offset + batch_size]
        ids, mask, intents, labels = collate(batch, pad_id, device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16):
            intent_logits, tag_logits = model(ids, mask)
        correct += (intent_logits.argmax(-1) == intents).sum().item()
        total += len(batch)
        predicted = tag_logits.argmax(-1)
        for row in range(len(batch)):
            keep = labels[row] != IGNORE
            gold = spans_from_tags(labels[row][keep].tolist())
            pred = spans_from_tags(predicted[row][keep].tolist())
            tp += len(gold & pred)
            fp += len(pred - gold)
            fn += len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"intent_acc": correct / total, "span_f1": f1, "span_precision": precision,
            "span_recall": recall}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="microsoft/MiniLM-L12-H384-uncased")
    parser.add_argument("--name", default="l12")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=8e-5)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--smoothing", type=float, default=0.0)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("device:", device, torch.cuda.get_device_name(0) if device.type == "cuda" else "")

    vocab_path = hf_hub_download(args.backbone, "vocab.txt")
    tokenizer = WordPiece.from_file(Path(vocab_path))
    train = [encode_example(tokenizer, e) for e in load_split("train")]
    val = [encode_example(tokenizer, e) for e in load_split("val")]
    print(f"train {len(train)}  val {len(val)}")

    model = build_model(args.backbone).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    steps = args.epochs * (len(train) // args.batch_size + 1)
    warmup = int(0.06 * steps)
    schedule = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lambda s: min((s + 1) / warmup, max(0.0, (steps - s) / (steps - warmup)))
    )
    intent_loss = nn.CrossEntropyLoss(label_smoothing=args.smoothing)
    tag_loss = nn.CrossEntropyLoss(ignore_index=IGNORE)

    out = ROOT / "ml" / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    log = (out / "log.jsonl").open("w", encoding="utf-8")
    best, started = -1.0, time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        random.shuffle(train)
        running = 0.0
        for offset in range(0, len(train), args.batch_size):
            ids, mask, intents, labels = collate(train[offset : offset + args.batch_size],
                                                 tokenizer.pad_id, device)  # fmt: skip
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16):
                intent_logits, tag_logits = model(ids, mask)
                loss = intent_loss(intent_logits.float(), intents) + tag_loss(
                    tag_logits.float().reshape(-1, len(TAGS)), labels.reshape(-1)
                )
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            schedule.step()
            running += loss.item()
        metrics = evaluate(model, val, tokenizer.pad_id, device)
        record = {"epoch": epoch, "train_loss": running / (len(train) / args.batch_size),
                  "seconds": round(time.time() - started, 1), **metrics}  # fmt: skip
        print(json.dumps(record))
        log.write(json.dumps(record) + "\n")
        log.flush()
        score = metrics["intent_acc"] + metrics["span_f1"]
        if score > best:
            best = score
            torch.save(model.state_dict(), out / "best.pt")
    model.load_state_dict(torch.load(out / "best.pt", map_location=device))
    dev = [encode_example(tokenizer, e) for e in load_split("dev")]
    dev_metrics = evaluate(model, dev, tokenizer.pad_id, device)
    print("dev (templates never trained on):", json.dumps(dev_metrics))
    config = {"backbone": args.backbone, "dev": dev_metrics, "vocab": str(vocab_path), "args": vars(args),
              "intents": list(INTENTS), "tags": list(TAGS), "seed": args.seed,
              "gpu": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
              "torch": torch.__version__, "train_seconds": round(time.time() - started, 1)}  # fmt: skip
    (out / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    print("saved", out / "best.pt")


if __name__ == "__main__":
    main()
