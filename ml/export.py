"""Export the trained reader as a small ONNX file the API can run on CPU, and calibrate it.

    ml/.venv/Scripts/python ml/export.py --name l12

Steps: export the PyTorch weights to ONNX, quantise the weights to int8 (kept only if accuracy on
the VALIDATION split stays within 0.3 points), fit a temperature so the confidence is honest and
pick the confidence thresholds on the DEV split (templates the model never trained on), and write
manifest.json with the SHA-256 of every file. The test sets are not used here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import torch

from common import DATA, ROOT, build_model, load_split
from app.ai.nlu.schema import ACTION_INTENTS, INTENTS
from app.ai.nlu.runtime import Reader

OUT = ROOT / "backend" / "app" / "ai" / "nlu" / "model"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_onnx(run: Path, config: dict, target: Path) -> None:
    model = build_model(config["backbone"])
    model.load_state_dict(torch.load(run / "best.pt", map_location="cpu"))
    model.eval()
    ids = torch.randint(5, 1000, (2, 17))
    mask = torch.ones_like(ids)
    torch.onnx.export(
        model, (ids, mask), str(target),
        input_names=["input_ids", "attention_mask"],
        output_names=["intent_logits", "tag_logits"],
        dynamic_axes={"input_ids": {0: "batch", 1: "length"},
                      "attention_mask": {0: "batch", 1: "length"},
                      "intent_logits": {0: "batch"}, "tag_logits": {0: "batch", 1: "length"}},
        opset_version=17, dynamo=False,
    )  # fmt: skip


def quantise(source: Path, target: Path) -> None:
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(str(source), str(target), weight_type=QuantType.QInt8)


def score(reader: Reader, examples: list[dict]) -> dict[str, float]:
    right = tp = fp = fn = 0
    for example in examples:
        prediction = reader.predict(example["text"])
        right += prediction.intent == example["intent"]
        gold = {(s, e, label) for s, e, label in example["spans"]}
        found = {(s.start, s.end, s.label) for s in prediction.spans}
        tp, fp, fn = tp + len(gold & found), fp + len(found - gold), fn + len(gold - found)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"intent_acc": right / len(examples), "span_f1": f1}


def write_manifest(directory: Path, extra: dict) -> None:
    files = {name: sha256(directory / name) for name in ("model.onnx", "vocab.txt")}
    manifest = {"files": files, **extra}
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    best, best_nll = 1.0, float("inf")
    for temperature in np.arange(0.5, 4.01, 0.05):
        scaled = logits / temperature
        scaled = scaled - scaled.max(axis=1, keepdims=True)
        log_probs = scaled - np.log(np.exp(scaled).sum(axis=1, keepdims=True))
        nll = -log_probs[np.arange(len(labels)), labels].mean()
        if nll < best_nll:
            best, best_nll = float(temperature), float(nll)
    return round(best, 2)


def thresholds(reader: Reader, dev: list[dict]) -> dict[str, float]:
    """Choose the confidence thresholds on the DEV split by running the agent's own logic.

    The attack threshold is the lowest one that falsely flags at most 0.5% of harmless messages.
    The intent and action thresholds then maximise routing accuracy while a message that is not a
    request for a quote, draft or approval is wrongly routed to one at most 0.5% of the time.
    """
    from datetime import date

    from app.ai.nlu.understanding import understand
    from app.engine.money import CURRENCY_EXPONENTS

    today = date(2026, 10, 15)
    rows = [(e, reader.predict(e["text"])) for e in dev]
    benign = [p for e, p in rows if e["intent"] != "ATTACK"]
    attack = 0.99
    for tau in np.arange(0.50, 0.995, 0.01):
        flagged = sum(p.intent == "ATTACK" and p.confidence >= tau for p in benign)
        if flagged / len(benign) <= 0.005:
            attack = round(float(tau), 2)
            break

    def route(name: str) -> str:
        return "HELP" if name in ("OUT_OF_SCOPE", "HELP") else name

    sample = rows[:: max(1, len(rows) // 2500)]
    best, best_score = (0.5, 0.9), (-1.0, 0.0)
    for tau_intent in np.arange(0.30, 0.96, 0.05):
        for tau_action in np.arange(0.50, 0.995, 0.05):
            limits = {"intent": float(tau_intent), "action": float(tau_action), "attack": attack}
            right = wrong_action = safe = 0
            for example, prediction in sample:
                got = understand(example["text"], today, CURRENCY_EXPONENTS, has_context=False,
                                 reader=reader, prediction=prediction, limits=limits)  # fmt: skip
                intent = "ATTACK" if got.attack else ("HELP" if got.out_of_scope else got.intent.value)
                right += route(intent) == route(example["intent"])
                if example["intent"] not in ACTION_INTENTS:
                    safe += 1
                    wrong_action += intent in ACTION_INTENTS
            accuracy = right / len(sample)
            if wrong_action / safe <= 0.005 and (accuracy, tau_intent) > best_score:
                best_score, best = (accuracy, float(tau_intent)), (float(tau_intent), float(tau_action))
    return {"intent": round(best[0], 2), "action": round(best[1], 2), "attack": attack}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="l12")
    parser.add_argument("--model-id", default="studyroute-nlu-v1")
    args = parser.parse_args()
    run = ROOT / "ml" / "runs" / args.name
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    work = run / "onnx"
    work.mkdir(exist_ok=True)
    fp32, int8 = work / "model_fp32.onnx", work / "model_int8.onnx"
    export_onnx(run, config, fp32)
    quantise(fp32, int8)
    shutil.copyfile(config["vocab"], OUT / "vocab.txt")
    val = load_split("val")

    def staged(model_file: Path) -> Reader:
        shutil.copyfile(model_file, OUT / "model.onnx")
        write_manifest(OUT, {"model_id": args.model_id})
        return Reader(OUT)

    full = score(staged(fp32), val)
    small = score(staged(int8), val)
    print("fp32 :", full, f"{fp32.stat().st_size / 1e6:.1f} MB")
    print("int8 :", small, f"{int8.stat().st_size / 1e6:.1f} MB")
    use_int8 = (
        full["intent_acc"] - small["intent_acc"] <= 0.003 and full["span_f1"] - small["span_f1"] <= 0.003
    )
    chosen = int8 if use_int8 else fp32
    reader = staged(chosen)

    dev = load_split("dev")
    logits, labels = [], []
    for example in dev:
        encoding = reader._tokenizer.encode(example["text"])  # noqa: SLF001
        ids = np.asarray([encoding.ids], dtype=np.int64)
        outputs = reader._session.run(None, {"input_ids": ids, "attention_mask": np.ones_like(ids)})  # noqa: SLF001
        logits.append(outputs[0][0])
        labels.append(INTENTS.index(example["intent"]))
    temperature = fit_temperature(np.asarray(logits), np.asarray(labels))
    write_manifest(OUT, {"model_id": args.model_id, "temperature": temperature})
    reader = Reader(OUT)
    limits = thresholds(reader, dev)
    data = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    write_manifest(
        OUT,
        {
            "model_id": args.model_id,
            "created": date.today().isoformat(),
            "base_model": config["backbone"],
            "base_model_license": "MIT",
            "quantisation": "int8 dynamic (weights)" if use_int8 else "none (fp32)",
            "temperature": temperature,
            "thresholds": limits,
            "validation": score(reader, val),
            "dev": score(reader, dev),
            "training": {k: config[k] for k in ("args", "gpu", "torch", "train_seconds", "seed")},
            "dataset": {
                "version": data["version"],
                "splits": {k: {"examples": v["examples"], "sha256": v["sha256"]}
                           for k, v in data["splits"].items()},
            },
            "intents": list(INTENTS),
        },
    )
    print("temperature", temperature, "thresholds", limits)
    print("wrote", OUT, f"{(OUT / 'model.onnx').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
