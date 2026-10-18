"""Run the shipped reader model on CPU with ONNX Runtime.

The model file is data, not code (an ONNX graph, not a pickle), and its SHA-256 is checked against
the manifest before it is loaded. Nothing here uses the network. If anything is missing or
wrong, ``load_reader`` returns None and the assistant keeps working on its rules.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.ai.nlu.schema import INTENTS, TAGS
from app.ai.nlu.slots import Span
from app.ai.nlu.tokenizer import WordPiece

logger = logging.getLogger("studyroute.ai")
# ONNX Runtime 1.31 ships Microsoft telemetry that is ON by default on Linux: about ten seconds
# after first use it contacts mobile.events.data.microsoft.com (found with a packet capture inside
# the container). StudyRoute promises no tracking and the reader needs no network, so switch it off
# before the library is imported, and again through its API.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
MODEL_DIR = Path(__file__).resolve().parent / "model"


@dataclass(frozen=True)
class Prediction:
    intent: str
    confidence: float  # calibrated probability of the chosen intent
    probabilities: dict[str, float]
    spans: list[Span]
    span_confidence: list[float]  # one per span: the weakest word in it


def _softmax(values, temperature: float = 1.0):  # type: ignore[no-untyped-def]
    import numpy as np

    scaled = np.asarray(values, dtype="float64") / temperature
    scaled = scaled - scaled.max(axis=-1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=-1, keepdims=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Reader:
    """The trained reader: one message in, an intent and the marked words out."""

    def __init__(self, directory: Path = MODEL_DIR) -> None:
        import onnxruntime as ort

        ort.disable_telemetry_events()
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        for name in ("model.onnx", "vocab.txt"):
            if _sha256(directory / name) != manifest["files"][name]:
                raise ValueError(f"{name} does not match its recorded SHA-256")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(directory / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self._tokenizer = WordPiece.from_file(directory / "vocab.txt")
        self.manifest = manifest
        self.model_id: str = manifest["model_id"]
        self.sha256: str = manifest["files"]["model.onnx"]
        self._temperature: float = float(manifest.get("temperature", 1.0))

    def predict(self, message: str) -> Prediction:
        import numpy as np

        encoding = self._tokenizer.encode(message)
        ids = np.asarray([encoding.ids], dtype=np.int64)
        mask = np.ones_like(ids)
        intent_logits, tag_logits = self._session.run(
            None, {"input_ids": ids, "attention_mask": mask}
        )
        probs = _softmax(intent_logits[0], self._temperature)
        best = int(probs.argmax())
        tag_probs = _softmax(tag_logits[0])
        word_tags = [int(tag_probs[position].argmax()) for position in encoding.first_piece]
        word_conf = [float(tag_probs[p].max()) for p in encoding.first_piece]
        spans, confidences = self._spans(message, encoding, word_tags, word_conf)
        return Prediction(
            INTENTS[best],
            float(probs[best]),
            {name: round(float(p), 4) for name, p in zip(INTENTS, probs, strict=True)},
            spans,
            confidences,
        )

    @staticmethod
    def _spans(message, encoding, word_tags, word_conf):  # type: ignore[no-untyped-def]
        spans: list[Span] = []
        confidences: list[float] = []
        first: int | None = None
        label = ""
        low = 1.0

        def close(last: int) -> None:
            if first is None:
                return
            start, end = encoding.words[first].start, encoding.words[last].end
            spans.append(Span(label, start, end, message[start:end]))
            confidences.append(low)

        for index, tag_id in enumerate(word_tags):
            tag = TAGS[tag_id]
            continues = tag.startswith("I-") and first is not None and tag[2:] == label
            if first is not None and not continues:
                close(index - 1)
                first = None
            if tag == "O":
                continue
            if first is None:
                first, label, low = index, tag[2:], word_conf[index]
            else:
                low = min(low, word_conf[index])
        close(len(word_tags) - 1)
        return Reader._join_split_numbers(message, spans, confidences)

    @staticmethod
    def _join_split_numbers(message, spans, confidences):  # type: ignore[no-untyped-def]
        """Rejoin an amount the model cut at a separator ("10" + "000" for "10,000")."""
        joined: list[Span] = []
        kept: list[float] = []
        for span, confidence in zip(spans, confidences, strict=True):
            before = joined[-1] if joined else None
            if (
                before is not None
                and before.label == span.label == "AMOUNT"
                and message[before.end : span.start] in (",", ".")
            ):
                joined[-1] = Span(
                    "AMOUNT", before.start, span.end, message[before.start : span.end]
                )
                kept[-1] = min(kept[-1], confidence)
            else:
                joined.append(span)
                kept.append(confidence)
        return joined, kept


def load_reader(mode: str = "auto", directory: Path = MODEL_DIR) -> Reader | None:
    """The reader, or None when it is switched off, not installed or fails its integrity check."""
    if mode == "off":
        return None
    try:
        return Reader(directory)
    except (ImportError, OSError, KeyError, ValueError) as exc:
        logger.warning("trained reader not used (%s); the assistant uses its rules", exc)
        return None
