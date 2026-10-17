"""Capture (what a model would be sent, the engine-correct answer) pairs from the real assistant.

    cd backend && ../ml/.venv/Scripts/python ../ml/explainer/generate_pairs.py --train 2400 --val 200 --test 500

A recording "model" is plugged into the assistant. It sees exactly the prompt a real model would see
(the engine's facts, masked, plus the question) and answers with an empty reply on purpose, so the
assistant's own guards reject it and fall back to the deterministic template. The template answer is
therefore the engine-correct reference for that exact prompt. Nothing is written by hand and no number
is invented: every figure in every reference was computed by the engine.

Questions come from the project's labelled sets (split so the wording of the test set is never seen in
training) plus a few hand-written student-cost and arrival questions. Scenarios vary the amount, the
currency, the charge code, the due date, the person asking and how far a payment has got.
Synthetic data only.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.explainer.prompt import draft_of, question_of  # noqa: E402
from app.ai.llm import LLMResult  # noqa: E402
from tests.helpers import World  # noqa: E402

DATA = ROOT / "ml" / "data" / "generated"
OUT = ROOT / "ml" / "explainer" / "data"

CORRIDORS = [
    ("GBP", "GB"),
    ("USD", "US"),
    ("EUR", "DE"),
    ("AUD", "AU"),
    ("CAD", "CA"),
    ("MYR", "MY"),
]
CHARGE_CODES = ["OUR", "OUR", "SHA", "BEN"]
SKIP_INTENTS = {"ATTACK"}  # blocked by the policy filter before any model is asked
EXTRA_QUESTIONS = {
    "STRESS": [
        "What if the taka falls 10 percent before I send?",
        "How much more would I pay if the exchange rate gets worse?",
        "Stress test this quote for a weaker taka.",
        "If bdt weakens by 15% what happens to my total?",
    ],
    "COSTS": [
        "Which city fits a budget of BDT 130,000 a month?",
        "How much is rent in London for a student?",
        "Which cities are cheapest to study in?",
        "What does a month in Manchester cost in taka?",
        "Is a studio or a shared flat cheaper in Johor Bahru?",
    ],
    "ARRIVAL": [
        "What should I do when I arrive in Germany?",
        "What do I need to sort out in my first week abroad?",
        "Give me the arrival checklist for the UK.",
        "What steps come before I fly?",
    ],
}


class RecordingLLM:
    """Sees the real prompt, answers with nothing, so the assistant falls back to its template."""

    provider = "recorder"
    model = "recorder-1"
    wants_draft = (
        True  # like the real local model, it is handed the engine's draft answer
    )

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, *, system: str, user: str) -> LLMResult:
        self.prompts.append(user)
        return LLMResult(text="{}", model=self.model)


def load_pool(*names: str) -> dict[str, list[str]]:
    pool: dict[str, list[str]] = {}
    for name in names:
        with gzip.open(DATA / f"{name}.jsonl.gz", "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                if row["intent"] not in SKIP_INTENTS:
                    pool.setdefault(row["intent"], []).append(row["text"])
    for intent, questions in EXTRA_QUESTIONS.items():
        pool.setdefault(intent, []).extend(questions)
    return pool


def pick_question(rng: random.Random, pool: dict[str, list[str]]) -> tuple[str, str]:
    intent = rng.choice(sorted(pool))
    return intent, rng.choice(pool[intent])


def make_quote(world: World, rng: random.Random) -> dict[str, Any]:
    currency, country = rng.choice(CORRIDORS)
    due = date(2026, 10, 20) + timedelta(days=rng.randint(0, 55))
    return world.quote(
        target={"amount_minor": rng.randint(50_000, 6_000_000), "currency": currency},
        destination_country=country,
        charge_code=rng.choice(CHARGE_CODES),
        due_date=due.isoformat(),
    )


def progress_payment(world: World, quote: dict[str, Any], stage: str) -> str | None:
    """Take a payment as far as the stage asks. Returns its id, or None for no payment."""
    if stage == "none":
        return None
    pid = str(world.draft(quote)["payment_id"])
    if stage == "draft":
        return pid
    approval = world.call("POST", f"/payments/{pid}/request-approval", idem=True).json()
    if stage == "pending":
        return pid
    world.approve(approval)
    return pid


def run_split(
    name: str,
    scenarios: int,
    per: int,
    pool: dict[str, list[str]],
    seed: int,
    out: Path,
) -> int:
    rng = random.Random(seed)
    recorder = RecordingLLM()
    written = 0
    seen: set[tuple[str, str]] = set()
    with tempfile.TemporaryDirectory() as tmp:
        world = World(Path(tmp), nlu_mode="auto", dialogue_mode="off")
        try:
            world.verify_kyc()
            world.allowlist()
            world.ctx.assistant = world.ctx.assistant.with_llm(recorder)
            with open(
                out / f"pairs_{name}.jsonl", "w", encoding="utf-8", newline="\n"
            ) as sink:
                for index in range(scenarios):
                    try:
                        quote = make_quote(world, rng)
                    except Exception as error:  # a rejected quote: skip the scenario
                        print(
                            f"  scenario {index} skipped: {type(error).__name__}",
                            file=sys.stderr,
                        )
                        continue
                    stage = rng.choices(
                        ["none", "draft", "pending", "approved"], weights=[5, 2, 2, 1]
                    )[0]
                    try:
                        payment_id = progress_payment(world, quote, stage)
                    except Exception:  # the demo recipient is in the UK: other corridors have no payment
                        payment_id = None
                    who = "student" if rng.random() < 0.15 else "parent"
                    for _ in range(per):
                        intent, question = pick_question(rng, pool)
                        context: dict[str, Any] = {"quote_id": quote["quote_id"]}
                        if payment_id and rng.random() < 0.7:
                            context["payment_id"] = payment_id
                        recorder.prompts.clear()
                        reply = world.call(
                            "POST", "/assistant/chat", who,
                            json={"message": question, "context": context},
                        )  # fmt: skip
                        if reply.status_code != 200 or not recorder.prompts:
                            continue
                        body = reply.json()
                        key = (recorder.prompts[0], body["reply"])
                        if key in seen:
                            continue
                        seen.add(key)
                        record = {
                            "split": name,
                            "scenario": index,
                            "who": who,
                            "intent": intent,
                            "question": question_of(recorder.prompts[0]),
                            "draft": draft_of(recorder.prompts[0]),
                            "mode": body.get("mode"),
                            "detected_intent": (body.get("understanding") or {}).get(
                                "intent"
                            ),
                        }
                        sink.write(json.dumps(record, ensure_ascii=False) + "\n")
                        written += 1
                    if (index + 1) % 100 == 0:
                        print(
                            f"  {name}: {index + 1}/{scenarios} scenarios, {written} pairs",
                            flush=True,
                        )
        finally:
            world.close()
    return written


def main() -> None:
    logging.disable(
        logging.INFO
    )  # the assistant logs every request; this run makes thousands
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--train", type=int, default=2400)
    parser.add_argument("--val", type=int, default=200)
    parser.add_argument("--test", type=int, default=500)
    parser.add_argument(
        "--per", type=int, default=5, help="questions asked in each scenario"
    )
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    pools = {
        "train": load_pool("train"),
        "val": load_pool("val"),
        # wording the model never trained on: the held-out templates, real bank questions, the hand-written sets
        "test": load_pool("test_heldout", "natural", "blind", "hard"),
    }
    sizes = {"train": args.train, "val": args.val, "test": args.test}
    for offset, name in enumerate(("train", "val", "test")):
        print(f"{name}: {sizes[name]} scenarios", flush=True)
        count = run_split(
            name, sizes[name], args.per, pools[name], args.seed + offset, OUT
        )
        print(f"{name}: wrote {count} pairs", flush=True)


if __name__ == "__main__":
    main()
