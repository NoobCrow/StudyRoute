"""Shared by training, export and evaluation: data loading, encoding and the model definition."""

from __future__ import annotations

import gzip
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.nlu.schema import INTENT_ID, INTENTS, TAG_ID, TAGS  # noqa: E402
from app.ai.nlu.tokenizer import Encoding, WordPiece  # noqa: E402

DATA = ROOT / "ml" / "data" / "generated"
IGNORE = -100


def load_split(name: str) -> list[dict]:
    with gzip.open(DATA / f"{name}.jsonl.gz", "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def word_tags(encoding: Encoding, spans: list[list]) -> list[int]:
    """BIO tag id for each word, from the character spans of the example."""
    tags = []
    previous: int | None = None  # index of the span the previous word was inside
    for word in encoding.words:
        tag, current = "O", None
        for index, (start, end, label) in enumerate(spans):
            if word.start >= start and word.end <= end:
                tag, current = f"{'I' if previous == index else 'B'}-{label}", index
                break
        previous = current
        tags.append(TAG_ID[tag])
    return tags


@dataclass
class Item:
    ids: list[int]
    intent: int
    labels: list[int]  # per piece: a tag id on the first piece of each word, IGNORE elsewhere


def encode_example(tokenizer: WordPiece, example: dict) -> Item:
    encoding = tokenizer.encode(example["text"])
    labels = [IGNORE] * len(encoding.ids)
    for position, tag in zip(encoding.first_piece, word_tags(encoding, example["spans"]), strict=True):
        labels[position] = tag
    return Item(encoding.ids, INTENT_ID[example["intent"]], labels)


def build_model(backbone: str):
    import torch
    from torch import nn
    from transformers import AutoModel

    class Reader(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = AutoModel.from_pretrained(backbone)
            hidden = self.encoder.config.hidden_size
            self.dropout = nn.Dropout(0.1)
            self.intent = nn.Linear(hidden, len(INTENTS))
            self.tags = nn.Linear(hidden, len(TAGS))

        def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor):
            states = self.encoder(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state
            states = self.dropout(states)
            return self.intent(states[:, 0]), self.tags(states)

    return Reader()
