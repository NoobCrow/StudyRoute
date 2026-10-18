"""Run the shipped explainer on CPU with ONNX Runtime.

Two ONNX graphs (an encoder and a decoder), a SentencePiece tokenizer and a small vocabulary
table. The files are data, not code, and each SHA-256 is checked against the manifest before
anything is loaded. Nothing here uses the network. If anything is missing or wrong,
``load_explainer`` returns None and the assistant keeps answering from the engine's own template.

The model was trained on a pruned vocabulary (only the pieces that occur in StudyRoute's questions
and answers, plus digits and punctuation), so ids are mapped in and out of it here."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("studyroute.ai")
# ONNX Runtime ships telemetry that is on by default on Linux. The reader switches it off, and
# the explainer does the same before the library is imported (see app.ai.nlu.runtime).
os.environ["ORT_DISABLE_TELEMETRY"] = "1"
MODEL_DIR = Path(__file__).resolve().parent / "model"
FILES = ("encoder.onnx", "decoder.onnx", "spiece.model", "vocab.json")
PAD, EOS, UNK = 0, 1, 2  # the same ids in the full and the pruned vocabulary


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class Rewrite:
    text: str
    tokens: int
    finished: bool  # False when it stopped because it ran out of tokens, not because it was done


class Explainer:
    """One question and the engine's draft in, a rewritten reply out. Greedy, no sampling."""

    def __init__(self, directory: Path = MODEL_DIR) -> None:
        import numpy as np
        import onnxruntime as ort
        import sentencepiece as spm

        ort.disable_telemetry_events()
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        for name in FILES:
            if _sha256(directory / name) != manifest["files"][name]:
                raise ValueError(f"{name} does not match its recorded SHA-256")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        providers = ["CPUExecutionProvider"]
        self._encoder = ort.InferenceSession(
            str(directory / "encoder.onnx"), options, providers=providers
        )
        self._decoder = ort.InferenceSession(
            str(directory / "decoder.onnx"), options, providers=providers
        )
        self._sp = spm.SentencePieceProcessor(model_file=str(directory / "spiece.model"))
        keep: list[int] = json.loads((directory / "vocab.json").read_text(encoding="utf-8"))["keep"]
        self._to_old = np.asarray(keep, dtype=np.int64)  # pruned id -> full id
        self._to_new = np.full(self._sp.get_piece_size() + 1, UNK, dtype=np.int64)  # full -> pruned
        self._to_new[self._to_old] = np.arange(len(keep), dtype=np.int64)
        self.manifest: dict[str, Any] = manifest
        self.model_id: str = manifest["model_id"]
        self.max_source: int = int(manifest["max_source_tokens"])
        self.max_new: int = int(manifest["max_new_tokens"])

    def rewrite(self, source: str) -> Rewrite:
        import numpy as np

        full_ids = [*self._sp.encode(source)[: self.max_source - 1], EOS]
        ids = self._to_new[np.asarray(full_ids, dtype=np.int64)][None, :]
        mask = np.ones_like(ids)
        hidden = self._encoder.run(None, {"input_ids": ids, "attention_mask": mask})[0]
        generated = [PAD]  # T5 starts decoding from the pad id
        finished = False
        for _ in range(self.max_new):
            logits = self._decoder.run(
                None,
                {
                    "decoder_input_ids": np.asarray([generated], dtype=np.int64),
                    "encoder_hidden_states": hidden,
                    "encoder_attention_mask": mask,
                },
            )[0][0, -1].copy()
            logits[UNK] = -np.inf  # never write an unknown piece
            nxt = int(logits.argmax())
            if nxt == EOS:
                finished = True
                break
            generated.append(nxt)
            if _loops(generated):
                break
        pieces = self._to_old[np.asarray(generated[1:], dtype=np.int64)].tolist()
        return Rewrite(self._sp.decode(pieces).strip(), len(pieces), finished)


def _loops(tokens: list[int]) -> bool:
    """A greedy model can get stuck repeating itself: stop when the last 4 pieces repeat 3 times."""
    return len(tokens) > 14 and tokens[-4:] == tokens[-8:-4] == tokens[-12:-8]


def load_explainer(mode: str = "auto") -> Explainer | None:
    """The shipped explainer, or None (mode off, files missing, a hash mismatch, no runtime)."""
    if mode == "off":
        return None
    try:
        explainer = Explainer()
    except Exception as error:  # the assistant works without it
        logger.warning("explainer not used: %s", error)
        return None
    logger.info("explainer loaded: %s", explainer.model_id)
    return explainer
