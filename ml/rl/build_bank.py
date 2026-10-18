"""Build the observation bank for the dialogue simulator.

    backend/.venv/Scripts/python ml/rl/build_bank.py

A simulated parent has a goal (a task, an amount, a due date, a period) and says it in different
words. Every sentence they could say is run through the REAL assistant reading pipeline (the
trained reader, the rule reader and the deterministic checks), and what the assistant would have
perceived is stored: the value it read and how sure it was. Training the dialogue policy against
this bank means the noise in its perception is the noise of the real system, not an invention.

Some sentences carry difficulty on purpose: a second, unrelated amount ("last year I paid ...")
and a date given as "sometime next month" that no reader can turn into a day.
"""

from __future__ import annotations

import gzip
import json
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "ml" / "data"), str(ROOT / "backend")]

import generate  # noqa: E402
import render  # noqa: E402
from markup import parse_markup  # noqa: E402

TODAY = generate.TODAY
OUT = ROOT / "ml" / "rl" / "bank"
PLAN = {
    ("A", "D"): [
        "I need to pay {M} tuition by {D}",
        "Help me pay {M} for fees, due {D}",
        "Please quote {M} for the university, deadline {D}",
        "{M} is due to my son's university on {D}. Can you plan it?",
        "pay {M} to the college before {D}",
    ],
    ("A",): [
        "I need to pay {M} for tuition",
        "Plan a payment of {M} to the university",
        "How do I send {M} to my daughter's college?",
        "i want to pay {M} fees",
        "Can you quote {M} please?",
    ],
    ("D",): [
        "I have to pay tuition by {D}",
        "Fees are due {D}, help me pay",
        "my daughter's university needs the money by {D}",
    ],
    (): [
        "I need to pay tuition",
        "help me pay my fees",
        "I want to send money to the university",
        "Can you help me with my son's tuition payment?",
    ],
}
CADENCE = {
    ("A", "Mo"): [
        "How often should I send {M} a month for {Mo}?",
        "Is it cheaper to send {M} monthly or all at once for {Mo}?",
        "I send {M} every month for {Mo}. Is there a better way?",
    ],
    ("A",): [
        "monthly or lump sum for {M} living costs?",
        "How should I send {M} every month to my son?",
        "what's the cheapest way to send {M} a month",
    ],
    ("Mo",): [
        "How should I send living costs for {Mo}?",
        "I need to cover {Mo} of rent for my daughter, what is best?",
    ],
    (): [
        "how often should I send money to my son?",
        "what is the best way to send living costs each month?",
        "monthly or lump sum?",
    ],
}
ANSWERS = {
    "amount": ["{M}", "it's {M}", "the amount is {M}", "{M} please", "around {M}"],
    "date": ["{D}", "by {D}", "it is due {D}", "the deadline is {D}"],
    "months": ["{Mo}", "for {Mo}", "it needs to cover {Mo}"],
}
UNREADABLE_DATES = ["sometime next month", "soon", "after the holidays", "early next year"]
DISTRACTORS = [
    "Last year I paid GBP 9,000.",
    "My brother paid 5,000 USD for his course.",
    "The invoice number is 4471.",
    "I have 2 kids studying abroad.",
]
_reader = None


def _init() -> None:
    global _reader
    from app.ai.nlu.runtime import load_reader

    _reader = load_reader("auto")
    if _reader is None:
        raise SystemExit("the trained reader is not available (is onnxruntime installed?)")


def make_goal(rng: random.Random, task: str) -> dict:
    code = render.pick_currency(rng)
    purpose = "LIVING" if task == "CADENCE" else "TUITION"
    value = render.amount_value(rng, purpose)
    due = TODAY + timedelta(days=rng.randint(3, 150))
    goal = {
        "task": task,
        "currency": code,
        "amount_minor": value * 100,
        "due_date": due.isoformat() if task == "PLAN" and rng.random() > 0.15 else None,
        "months": rng.randint(2, 12) if task == "CADENCE" else None,
    }
    return goal


def say(rng: random.Random, template: str, goal: dict, *, hard: bool) -> str:
    """The parent's sentence for this goal, from a template with {M}, {D} and {Mo}."""
    due = date.fromisoformat(goal["due_date"]) if goal["due_date"] else None
    purpose = "LIVING" if goal["task"] == "CADENCE" else "TUITION"
    money = render.money(
        rng,
        purpose,
        value=goal["amount_minor"] // 100,
        code=goal["currency"],
        with_currency=0.93 if hard else 1.0,
    )
    if "{D}" in template:
        unreadable = hard and rng.random() < 0.18
        date_text = (
            rng.choice(UNREADABLE_DATES) if unreadable or due is None else render.date_for(rng, due)
        )
    else:
        date_text = ""
    months = render.months_for(rng, goal["months"]) if "{Mo}" in template and goal["months"] else ""
    marked = template.replace("{M}", money).replace("{D}", date_text).replace("{Mo}", months)
    if rng.random() < 0.3:
        prefix = rng.choice(generate.PREFIXES)
        marked = prefix + (marked[:1].lower() + marked[1:] if prefix else marked)
    if hard and rng.random() < 0.2:
        marked = f"{marked} {rng.choice(DISTRACTORS)}"
    text, _ = parse_markup(marked)
    if rng.random() < 0.15:
        text = generate._typo(rng, text)
    return text.lower() if rng.random() < 0.15 else text


def perceive(text: str) -> dict:
    """What the assistant's own reading pipeline makes of one sentence."""
    from app.ai.nlu.understanding import understand
    from app.engine.money import CURRENCY_EXPONENTS

    got = understand(text, TODAY, CURRENCY_EXPONENTS, has_context=False, reader=_reader)
    p = got.parsed
    values = {
        "amount": [p.amount_minor, p.currency] if p.has_amount else None,
        "date": p.due_date.isoformat() if p.due_date else None,
        "months": p.months,
    }
    slots = {}
    for name, state in got.evidence.items():
        slots[name] = {
            "value": values[name],
            "present": state.present,
            "conflict": state.conflict,
            "source": state.source,
            "conf": round(state.confidence, 4),
        }
    return {
        "text": text,
        "intent": got.intent.value,
        "intent_conf": round(got.confidence or 0, 4),
        "attack": got.attack,
        "amount_spans": got.amount_candidates,
        "slots": slots,
    }


def build_goal(args: tuple[int, int]) -> dict:
    index, seed = args
    rng = random.Random(f"{seed}:{index}")
    task = "PLAN" if rng.random() < 0.7 else "CADENCE"
    goal = make_goal(rng, task)
    table = PLAN if task == "PLAN" else CADENCE
    first = []
    for subset, templates in table.items():
        for _ in range(2):
            text = say(rng, rng.choice(templates), goal, hard=True)
            first.append({"subset": list(subset), **perceive(text)})
    answers: dict[str, list[dict]] = {}
    needed = ["amount", "date"] if task == "PLAN" else ["amount", "months"]
    for slot in needed:
        if slot == "date" and goal["due_date"] is None:
            continue
        answers[slot] = [
            perceive(say(rng, rng.choice(ANSWERS[slot]), goal, hard=False)) for _ in range(3)
        ]
    return {"goal": goal, "first": first, "answers": answers}


def main(goals: int = 6000, seed: int = 20261015, workers: int = 10) -> None:
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=workers, initializer=_init) as pool:
        entries = list(pool.map(build_goal, [(i, seed) for i in range(goals)], chunksize=20))
    path = OUT / "bank.jsonl.gz"
    lines = "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in entries) + "\n"
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(lines.encode("utf-8"))
    print(f"wrote {path} ({goals} goals)")


if __name__ == "__main__":
    main()
