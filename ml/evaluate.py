"""Measure the shipped model against the rule-based baseline. Writes docs/AI_EVALUATION.md.

    backend/.venv/Scripts/python ml/evaluate.py

Three systems are compared on the same held-back data:

* rules  the assistant's original regex reader (request_parser + intents + policy filter)
* reader the trained model on its own (raw prediction, no thresholds)
* agent  what the product actually runs: reader + deterministic checks + thresholds + policy

Test data the model never trained on and no threshold was tuned on: test (new values in the
trained templates), test_heldout (templates never seen), hard (136 hand-written messages) and
oos_public (Banking77's own test split). HELP and OUT_OF_SCOPE are one routing class (both answer
with the help text), which is the kindest reading for the baseline.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "ml"))

from common import load_split  # noqa: E402

from app.ai.intents import choose_intent  # noqa: E402
from app.ai.nlu.runtime import load_reader  # noqa: E402
from app.ai.nlu.schema import ACTION_INTENTS  # noqa: E402
from app.ai.nlu.slots import read_slots  # noqa: E402
from app.ai.nlu.understanding import understand  # noqa: E402
from app.ai.policy import check_text  # noqa: E402
from app.ai.request_parser import parse_request  # noqa: E402
from app.engine.money import CURRENCY_EXPONENTS  # noqa: E402

TODAY = date(2026, 10, 15)
SETS = ("test", "test_heldout", "natural", "blind", "hard", "oos_public")
FIELDS = ("amount", "due_date", "months")


@dataclass
class Result:
    intent: str  # routing class; "ATTACK" when the message is blocked
    amount: tuple[int, str] | None
    due: str | None
    months: int | None

    @property
    def acts(self) -> bool:
        return self.intent in ACTION_INTENTS


def route(name: str) -> str:
    return "HELP" if name in ("OUT_OF_SCOPE", "HELP") else name


def rules_system(text: str) -> Result:
    parsed = parse_request(text, CURRENCY_EXPONENTS, TODAY)
    if check_text(text).blocked:
        intent = "ATTACK"
    else:
        intent = route(choose_intent(text, parsed, has_context=False).value)
    amount = (parsed.amount_minor, parsed.currency) if parsed.has_amount else None
    return Result(intent, amount, parsed.due_date.isoformat() if parsed.due_date else None, parsed.months)  # type: ignore[arg-type]


def reader_system(reader, text: str) -> Result:  # type: ignore[no-untyped-def]
    prediction = reader.predict(text)
    values = read_slots(prediction.spans, TODAY, CURRENCY_EXPONENTS)
    amount = (values.amount_minor, values.currency) if values.amount_minor and values.currency else None
    return Result(route(prediction.intent), amount,
                  values.due_date.isoformat() if values.due_date else None, values.months)  # fmt: skip


def agent_system(reader, text: str) -> Result:  # type: ignore[no-untyped-def]
    blocked = check_text(text).blocked
    understood = understand(text, TODAY, CURRENCY_EXPONENTS, has_context=False, reader=reader)
    parsed = understood.parsed
    intent = "ATTACK" if blocked or understood.attack else route(understood.intent.value)
    if understood.out_of_scope:
        intent = "HELP"
    amount = (parsed.amount_minor, parsed.currency) if parsed.has_amount else None
    return Result(intent, amount, parsed.due_date.isoformat() if parsed.due_date else None, parsed.months)  # type: ignore[arg-type]


def gold_of(example: dict) -> Result:
    gold = example["gold"]
    amount = (gold["amount_minor"], gold["currency"]) if gold["amount_minor"] and gold["currency"] else None
    return Result(route(example["intent"]), amount, gold["due_date"], gold["months"])


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - spread), min(1.0, centre + spread)


def macro_f1(pairs: list[tuple[str, str]]) -> float:
    scores = []
    for label in sorted({g for g, _ in pairs}):
        tp = sum(g == p == label for g, p in pairs)
        fp = sum(p == label and g != label for g, p in pairs)
        fn = sum(g == label and p != label for g, p in pairs)
        scores.append(2 * tp / (2 * tp + fp + fn) if tp else 0.0)
    return sum(scores) / len(scores)


def slot_f1(golds: list[Result], preds: list[Result], field: str) -> dict[str, float]:
    tp = fp = fn = 0
    for gold, pred in zip(golds, preds, strict=True):
        want, got = getattr(gold, field if field != "due_date" else "due"), getattr(pred, field if field != "due_date" else "due")
        if want is not None and got == want:
            tp += 1
        else:
            fp += got is not None
            fn += want is not None
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    if tp + fn == 0:
        return {"precision": None, "recall": None, "f1": None, "gold": 0, "false_values": fp}
    return {"precision": precision, "recall": recall, "f1": f1, "gold": tp + fn}


def evaluate(examples: list[dict], system) -> dict:  # type: ignore[no-untyped-def]
    golds = [gold_of(e) for e in examples]
    preds = [system(e["text"]) for e in examples]
    pairs = [(g.intent, p.intent) for g, p in zip(golds, preds, strict=True)]
    correct = sum(g == p for g, p in pairs)
    attacks = [(g, p) for g, p in zip(golds, preds, strict=True) if g.intent == "ATTACK"]
    benign = [(g, p) for g, p in zip(golds, preds, strict=True) if g.intent != "ATTACK"]
    safe_gold = [(g, p) for g, p in zip(golds, preds, strict=True) if g.intent not in ACTION_INTENTS]
    task = [(g, p, e) for (g, p), e in zip(zip(golds, preds, strict=True), examples, strict=True)
            if g.intent in ("PLAN", "CADENCE")]  # fmt: skip
    task_ok = sum(
        g.intent == p.intent and all(getattr(g, f) == getattr(p, f) for f in ("amount", "due", "months"))
        for g, p, _ in task
    )
    low, high = wilson(correct, len(pairs))
    out = {
        "n": len(examples),
        "routing_accuracy": correct / len(pairs),
        "routing_ci95": [round(low, 4), round(high, 4)],
        "macro_f1": macro_f1(pairs),
        "slots": {f: slot_f1(golds, preds, f) for f in FIELDS},
        "attack_n": len(attacks),
        "attack_blocked": sum(p.intent == "ATTACK" for _, p in attacks) / len(attacks) if attacks else None,
        "benign_blocked": sum(p.intent == "ATTACK" for _, p in benign) / len(benign) if benign else None,
        "wrongly_starts_action": sum(p.acts for _, p in safe_gold) / len(safe_gold) if safe_gold else None,
        "task_n": len(task),
        "task_success": task_ok / len(task) if task else None,
    }
    by_group: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for example, (g, p) in zip(examples, zip(golds, preds, strict=True), strict=True):
        group = example.get("group")
        if group:
            by_group[group][1] += 1
            by_group[group][0] += g.intent == p.intent
    out["by_group"] = {k: {"correct": v[0], "n": v[1]} for k, v in sorted(by_group.items())}
    return out


def latency(reader, texts: list[str]) -> dict[str, float]:  # type: ignore[no-untyped-def]
    for text in texts[:20]:
        reader.predict(text)
    times = []
    for text in texts:
        started = time.perf_counter()
        reader.predict(text)
        times.append((time.perf_counter() - started) * 1000)
    times.sort()
    return {"median_ms": round(statistics.median(times), 2),
            "p95_ms": round(times[int(0.95 * len(times))], 2), "n": len(times)}  # fmt: skip


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def main() -> None:
    reader = load_reader("auto")
    if reader is None:
        raise SystemExit("the trained reader is not available (is onnxruntime installed?)")
    data = {name: load_split(name) for name in SETS}
    systems = {
        "rules": rules_system,
        "reader": lambda t: reader_system(reader, t),
        "agent": lambda t: agent_system(reader, t),
    }
    results = {
        s: {name: evaluate(examples, fn) for name, examples in data.items()}
        for s, fn in systems.items()
    }
    timing = latency(reader, [e["text"] for e in data["hard"] + data["test"][:300]])
    manifest = reader.manifest
    report = {"model": {k: manifest.get(k) for k in ("model_id", "base_model", "quantisation",
              "temperature", "thresholds", "created", "training")},
              "model_bytes": (Path(ROOT / "backend/app/ai/nlu/model/model.onnx")).stat().st_size,
              "model_sha256": manifest["files"]["model.onnx"],
              "latency_cpu": timing, "results": results,
              "data": {k: v["examples"] for k, v in manifest["dataset"]["splits"].items()}}  # fmt: skip
    evidence = ROOT / "submission" / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "ai_evaluation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )
    (ROOT / "docs" / "AI_EVALUATION.md").write_text(render(report, data), encoding="utf-8")
    print(render_console(results))


def render_console(results: dict) -> str:
    lines = []
    for name in SETS:
        lines.append(f"== {name}")
        for system in ("rules", "reader", "agent"):
            r = results[system][name]
            lines.append(
                f"  {system:7} routing {pct(r['routing_accuracy'])}  macroF1 {pct(r['macro_f1'])}  "
                f"amount F1 {pct(r['slots']['amount']['f1'])}  date F1 {pct(r['slots']['due_date']['f1'])}  "
                f"task {pct(r['task_success'])}  attack blocked {pct(r['attack_blocked'])}  "
                f"benign blocked {pct(r['benign_blocked'])}  wrong action {pct(r['wrongly_starts_action'])}"
            )
    return "\n".join(lines)


def render(report: dict, data: dict) -> str:
    results, model = report["results"], report["model"]
    size = report["model_bytes"] / 1e6
    out = [
        "# AI evaluation: the trained reader against the rule-based baseline",
        "",
        "Generated by `ml/evaluate.py` from the shipped model "
        f"(`{model['model_id']}`, {size:.1f} MB, {model['quantisation']}); do not edit by hand. "
        "Every number below is measured on data the model never trained on and no threshold was "
        "tuned on, with one labelled exception: the hard set guided error analysis during "
        "development, so it is a diagnostic. The blind set was written after the model was frozen "
        "and evaluated once. See [AI_AGENT.md](AI_AGENT.md) for the design, the dataset card and "
        "the limits.",
        "",
        "Systems: **rules** is the assistant's original regex reader plus its policy filter. "
        "**reader** is the trained model alone. **agent** is what the product runs: the reader, "
        "the deterministic checks, the confidence thresholds and the policy filter together.",
        "",
        "Routing accuracy treats HELP and OUT_OF_SCOPE as one class, because both answer with the "
        "help text; this is the kindest reading for the baseline.",
        "",
    ]
    labels = {
        "test": "Test: new values in the training templates (easy, a sanity check)",
        "test_heldout": "Held-out templates: wording the model never saw",
        "blind": "Blind set: hand-written after the model was frozen, evaluated once",
        "hard": "Hard set: hand-written, used for error analysis during development (a diagnostic)",
        "natural": "Natural questions: Banking77 test messages mapped to StudyRoute intents",
        "oos_public": "Out of scope: Banking77 test questions (card, ATM and account admin)",
    }
    for name in SETS:
        n = results["rules"][name]["n"]
        out += [f"## {labels[name]} (n = {n})", "",
                "| System | Routing accuracy (95% CI) | Macro F1 | Amount F1 | Date F1 | Months F1 | Task success | Attacks blocked | Harmless blocked | Wrongly starts an action |",  # noqa: E501
                "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for system in ("rules", "reader", "agent"):
            r = results[system][name]
            lo, hi = r["routing_ci95"]
            out.append(
                f"| {system} | {pct(r['routing_accuracy'])} ({100*lo:.1f}-{100*hi:.1f}) | "
                f"{pct(r['macro_f1'])} | {pct(r['slots']['amount']['f1'])} | "
                f"{pct(r['slots']['due_date']['f1'])} | {pct(r['slots']['months']['f1'])} | "
                f"{pct(r['task_success'])} | {pct(r['attack_blocked'])} | {pct(r['benign_blocked'])} | "
                f"{pct(r['wrongly_starts_action'])} |"
            )
        out.append("")
    hard = results["agent"]["hard"]["by_group"]
    rules_hard = results["rules"]["hard"]["by_group"]
    out += ["## The hard set by kind of message", "",
            "| Group | n | rules correct | agent correct |", "|---|---|---|---|"]  # fmt: skip
    for group, cell in hard.items():
        out.append(f"| {group} | {cell['n']} | {rules_hard[group]['correct']} | {cell['correct']} |")
    t = report["latency_cpu"]
    out += [
        "",
        "## Cost",
        "",
        f"The model runs on CPU with ONNX Runtime: median {t['median_ms']} ms and 95th percentile "
        f"{t['p95_ms']} ms per message (n = {t['n']}, 2 threads). The file is {size:.1f} MB.",
        "",
        "## How to read this honestly",
        "",
        "* The training and test messages are mostly **synthetic**. The model learns the patterns of "
        "the generator, so the first table is a sanity check and the held-out and hard tables carry "
        "the weight. No real parent's messages were used.",
        "* The hard set is small (136), so differences of a few points are within noise; the "
        "confidence intervals show it.",
        "* A fixed phrase list is hard to beat on messages it was written for. The reader's "
        "advantage is on wording the rules do not contain; the agent column shows what is kept "
        "once the deterministic checks and thresholds are applied.",
        "* \"Wrongly starts an action\" counts messages that are not requests for a quote, draft or "
        "approval request but were routed to one. Even then the assistant only proposes: it "
        "cannot approve, and a person still clicks.",
    ]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
