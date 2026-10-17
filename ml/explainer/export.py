"""Shrink the trained student, export it to ONNX int8 and write it where the backend loads it from.

    ml/.venv/Scripts/python ml/explainer/export.py --run explainer-v1

Three things happen, and each is checked:
1. The vocabulary is pruned to the pieces that occur in StudyRoute's questions and answers (plus every
   digit and punctuation piece), so the embedding and output tables shrink from 32,128 rows to a few
   thousand. The pruned model must write the same answers as the full one on held-out examples.
2. The encoder and the decoder are exported to ONNX and the weights quantised to int8. The ONNX model
   must still write (nearly) the same answers as the PyTorch one.
3. The files, their SHA-256 and the training facts are written to backend/app/ai/explainer/model/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic
import sentencepiece as spm
from huggingface_hub import hf_hub_download
from transformers import T5ForConditionalGeneration

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ml" / "explainer" / "data"
RUNS = ROOT / "ml" / "explainer" / "runs"
OUT = ROOT / "backend" / "app" / "ai" / "explainer" / "model"
MAX_SOURCE, MAX_NEW = 512, 200
PAD, EOS, UNK = 0, 1, 2
BASE = "google/flan-t5-small"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_text(question: str, draft: str) -> str:
    return f"rewrite the draft to answer the question | question: {question[:300]} | flags: none | draft: {draft[:2000]}"


def kept_pieces(sp: spm.SentencePieceProcessor) -> list[int]:
    """Every piece id used by the data, plus all digit and punctuation pieces and the special ids."""
    keep: set[int] = {PAD, EOS, UNK}
    for split in ("train", "val", "test"):
        with open(DATA / f"verified_{split}.jsonl", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                for text in (
                    source_text(row["question"], row["draft"]),
                    row["draft"],
                    *row["rewrites"],
                ):
                    keep.update(sp.encode(text))
    plain = re.compile(r"^▁?[0-9.,:;%/\-+()'\"!?&@#$*=<>\[\]{}|_]+$")
    for index in range(sp.get_piece_size()):
        piece = sp.id_to_piece(index)
        if plain.match(piece) or len(piece.strip("▁")) == 1:
            keep.add(index)
    return sorted(keep)


def prune(
    model: T5ForConditionalGeneration, keep: list[int]
) -> T5ForConditionalGeneration:
    rows = torch.tensor(keep)
    d_model = model.config.d_model
    shared = torch.nn.Embedding(len(keep), d_model)
    shared.weight.data = model.shared.weight.data[rows].clone()
    head = torch.nn.Linear(d_model, len(keep), bias=False)
    head.weight.data = model.lm_head.weight.data[rows].clone()
    model.shared = shared
    model.encoder.embed_tokens = shared
    model.decoder.embed_tokens = shared
    model.lm_head = head
    model.config.vocab_size = len(keep)
    return model


class Encoder(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.encoder = model.encoder

    def forward(self, input_ids, attention_mask):
        return self.encoder(
            input_ids=input_ids, attention_mask=attention_mask
        ).last_hidden_state


class Decoder(torch.nn.Module):
    def __init__(self, model):
        super().__init__()
        self.decoder, self.head = model.decoder, model.lm_head

    def forward(self, decoder_input_ids, encoder_hidden_states, encoder_attention_mask):
        hidden = self.decoder(
            input_ids=decoder_input_ids,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
        ).last_hidden_state
        return self.head(
            hidden[:, -1:, :]
        )  # only the last position is needed to pick the next piece


@torch.no_grad()
def greedy_torch(model, ids: list[int], to_new: np.ndarray | None) -> list[int]:
    """Greedy decode in PyTorch. `ids` are full-vocabulary ids; returns pruned (or full) output ids."""
    source = torch.tensor([list(to_new[ids]) if to_new is not None else ids]).cuda()
    mask = torch.ones_like(source)
    out = model.generate(
        input_ids=source,
        attention_mask=mask,
        max_new_tokens=MAX_NEW,
        do_sample=False,
        num_beams=1,
    )
    return out[0].tolist()[1:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", default="explainer-v1")
    parser.add_argument(
        "--check",
        type=int,
        default=150,
        help="held-out examples used to compare the versions",
    )
    args = parser.parse_args()

    checkpoint = RUNS / args.run / "best"
    spiece = Path(hf_hub_download(BASE, "spiece.model"))
    sp = spm.SentencePieceProcessor(model_file=str(spiece))
    keep = kept_pieces(sp)
    print(f"pruned vocabulary: {len(keep)} of {sp.get_piece_size()} pieces", flush=True)

    full = T5ForConditionalGeneration.from_pretrained(checkpoint).cuda().eval()
    small = (
        prune(T5ForConditionalGeneration.from_pretrained(checkpoint), keep)
        .cuda()
        .eval()
    )
    to_new = np.full(sp.get_piece_size() + 1, UNK, dtype=np.int64)
    to_new[np.asarray(keep)] = np.arange(len(keep))

    with open(DATA / "verified_test.jsonl", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle][: args.check]
    sources = [
        [*sp.encode(source_text(r["question"], r["draft"]))[: MAX_SOURCE - 1], EOS]
        for r in rows
    ]
    same = 0
    full_out, small_out = [], []
    for ids in sources:
        a = sp.decode([i for i in greedy_torch(full, ids, None) if i > EOS]).strip()
        b_ids = greedy_torch(small, ids, to_new)
        b = sp.decode([keep[i] for i in b_ids if i > EOS]).strip()
        full_out.append(a)
        small_out.append(b)
        same += a == b
    print(f"pruning changed {len(rows) - same} of {len(rows)} answers", flush=True)

    # ---- ONNX
    OUT.mkdir(parents=True, exist_ok=True)
    work = RUNS / args.run / "onnx"
    work.mkdir(exist_ok=True)
    small = small.cpu().eval()
    enc_in = torch.randint(3, 100, (1, 40))
    enc_mask = torch.ones_like(enc_in)
    torch.onnx.export(
        Encoder(small),
        (enc_in, enc_mask),
        str(work / "encoder_fp32.onnx"),
        input_names=["input_ids", "attention_mask"],
        output_names=["hidden"],
        dynamic_axes={
            "input_ids": {0: "b", 1: "s"},
            "attention_mask": {0: "b", 1: "s"},
            "hidden": {0: "b", 1: "s"},
        },
        opset_version=17,
        dynamo=False,
    )
    hidden = Encoder(small)(enc_in, enc_mask)
    dec_in = torch.randint(3, 100, (1, 7))
    torch.onnx.export(
        Decoder(small),
        (dec_in, hidden, enc_mask),
        str(work / "decoder_fp32.onnx"),
        input_names=[
            "decoder_input_ids",
            "encoder_hidden_states",
            "encoder_attention_mask",
        ],
        output_names=["logits"],
        dynamic_axes={
            "decoder_input_ids": {0: "b", 1: "t"},
            "encoder_hidden_states": {0: "b", 1: "s"},
            "encoder_attention_mask": {0: "b", 1: "s"},
            "logits": {0: "b"},
        },
        opset_version=17,
        dynamo=False,
    )
    for name in ("encoder", "decoder"):
        quantize_dynamic(
            work / f"{name}_fp32.onnx",
            OUT / f"{name}.onnx",
            weight_type=QuantType.QInt8,
        )
        print(
            f"{name}: fp32 {(work / f'{name}_fp32.onnx').stat().st_size / 1e6:.1f} MB -> int8 {(OUT / f'{name}.onnx').stat().st_size / 1e6:.1f} MB",
            flush=True,
        )

    # ---- the tokenizer and vocabulary table the runtime needs
    shutil.copy(spiece, OUT / "spiece.model")
    (OUT / "vocab.json").write_text(json.dumps({"keep": keep}), encoding="utf-8")

    # ---- compare ONNX int8 with PyTorch on held-out examples
    options = ort.SessionOptions()
    encoder = ort.InferenceSession(
        str(OUT / "encoder.onnx"), options, providers=["CPUExecutionProvider"]
    )
    decoder = ort.InferenceSession(
        str(OUT / "decoder.onnx"), options, providers=["CPUExecutionProvider"]
    )
    onnx_same, started = 0, time.time()
    for ids, expected in zip(sources, small_out, strict=True):
        new_ids = to_new[np.asarray(ids)][None, :]
        mask = np.ones_like(new_ids)
        h = encoder.run(None, {"input_ids": new_ids, "attention_mask": mask})[0]
        seq = [PAD]
        for _ in range(MAX_NEW):
            logits = decoder.run(
                None,
                {
                    "decoder_input_ids": np.asarray([seq]),
                    "encoder_hidden_states": h,
                    "encoder_attention_mask": mask,
                },
            )[0][0, -1].copy()
            logits[UNK] = -np.inf
            nxt = int(logits.argmax())
            if nxt == EOS:
                break
            seq.append(nxt)
        text = sp.decode([keep[i] for i in seq[1:]]).strip()
        onnx_same += text == expected
    seconds = (time.time() - started) / len(sources)
    print(
        f"int8 ONNX matches the PyTorch answer on {onnx_same} of {len(sources)}; {seconds:.2f} s per answer on this CPU",
        flush=True,
    )

    manifest = {
        "model_id": f"studyroute-{args.run}",
        "base_model": "google/flan-t5-small",
        "base_model_license": "Apache-2.0",
        "teacher_model": "Qwen/Qwen2.5-1.5B-Instruct (Apache-2.0), used only to propose training targets",
        "created": time.strftime("%Y-%m-%d"),
        "max_source_tokens": MAX_SOURCE,
        "max_new_tokens": MAX_NEW,
        "vocabulary": {"kept_pieces": len(keep), "full_pieces": sp.get_piece_size()},
        "export_checks": {
            "examples": len(sources),
            "pruned_matches_full": same,
            "int8_onnx_matches_pytorch": onnx_same,
            "seconds_per_answer_cpu": round(seconds, 2),
        },
        "training": json.loads(
            (RUNS / args.run / "log.json").read_text(encoding="utf-8")
        ),
        "files": {
            name: sha256(OUT / name)
            for name in ("encoder.onnx", "decoder.onnx", "spiece.model", "vocab.json")
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("written to", OUT)


if __name__ == "__main__":
    main()
