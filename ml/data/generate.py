"""Compose labelled messages from templates. Pure standard library, fully seeded.

    python ml/data/build_dataset.py        # writes ml/data/generated/*.jsonl.gz and a manifest

An example is {"text", "intent", "spans": [[start, end, LABEL], ...], "family"}. Spans are exact
character ranges of the text. The dataset builder also runs every span through the project's own
normalizer; an example whose span cannot be read as a value is dropped, so the labels are never
ahead of what the deterministic code can understand.
"""

from __future__ import annotations

import random
import re
from datetime import date

import render
import templates
from markup import parse_markup

TODAY = date(2026, 10, 15)  # the sandbox date the relative phrases are anchored to
PLACEHOLDER = re.compile(r"<(\w+)>")
PREFIXES = [
    "", "", "", "", "", "Hi, ", "Hello, ", "Hi StudyRoute, ", "Assalamu alaikum, ", "Dear sir, ",
    "Please ", "Kindly ", "Quick question: ", "Hey, ", "Sir, ", "Excuse me, ",
]  # fmt: skip
SUFFIXES = [
    "", "", "", "", "", " Thanks.", " Thank you!", " Please advise.", " Urgent.", " asap",
    " thanks in advance", " please help",
]  # fmt: skip
ENDINGS = ["", ".", "?", "!"]
_LONG_WORD = re.compile(r"[A-Za-z]{5,}")


def _typo(rng: random.Random, chunk: str) -> str:
    """One slip in one word of the template's own wording (never inside a labelled value)."""
    found = list(_LONG_WORD.finditer(chunk))
    if not found:
        return chunk
    match = rng.choice(found)
    word = match.group()
    i = rng.randrange(1, len(word) - 1)
    kind = rng.choice(["swap", "drop", "double"])
    if kind == "swap":
        word = word[:i] + word[i + 1] + word[i] + word[i + 2 :]
    elif kind == "drop":
        word = word[:i] + word[i + 1 :]
    else:
        word = word[:i] + word[i] + word[i:]
    return chunk[: match.start()] + word + chunk[match.end() :]


def _fill(name: str, rng: random.Random, state: dict[str, str]) -> str:
    if name in ("prov", "prov2") and "prov" not in state:
        first, second = rng.sample("ABC", 2)
        state["prov"], state["prov2"] = first, second
    if name in ("charge", "charge2") and "charge" not in state:
        first, second = rng.sample(["OUR", "SHA", "BEN"], 2)
        state["charge"], state["charge2"] = first, second
    simple = {
        "money": lambda: render.money(rng, "TUITION"),
        "money_l": lambda: render.money(rng, "LIVING"),
        "date": lambda: render.date_phrase(rng, TODAY),
        "dur": lambda: render.duration(rng),
        "purpose": lambda: render.purpose(rng),
        "purpose_l": lambda: render.purpose(rng, "LIVING"),
        "prov": lambda: render.provider_with(rng, state["prov"]),
        "prov2": lambda: render.provider_with(rng, state["prov2"]),
        "charge": lambda: render.charge_with(rng, state["charge"]),
        "charge2": lambda: render.charge_with(rng, state["charge2"]),
        "univ": lambda: rng.choice(render.UNIVERSITIES),
        "junk": lambda: rng.choice(render.JUNK),
        "id": lambda: str(rng.randrange(100000, 999999)),
        "acct": lambda: str(rng.randrange(10_000_000, 99_999_999)),
        "verb": lambda: rng.choice(templates.VERBS),
        "city": lambda: rng.choice(templates.CITIES),
        "country": lambda: rng.choice(templates.COUNTRIES),
        "thing": lambda: rng.choice(templates.THINGS),
        "task": lambda: rng.choice(templates.TASKS),
    }
    return simple[name]()


def compose(
    template: str, rng: random.Random, *, noisy: bool = True
) -> tuple[str, list[tuple[int, int, str]]]:
    """Fill a template. Returns the clean text and its spans."""
    pieces = PLACEHOLDER.split(template)  # literal, name, literal, name, ...
    state: dict[str, str] = {}
    out: list[str] = []
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            out.append(_typo(rng, piece) if noisy and rng.random() < 0.06 else piece)
        else:
            out.append(_fill(piece, rng, state))
    marked = "".join(out)
    if noisy and not marked.startswith("[["):
        prefix = rng.choice(PREFIXES)
        if prefix and not marked.startswith(("I ", "I'")):
            marked = marked[:1].lower() + marked[1:]
        marked = prefix + marked + rng.choice(SUFFIXES)
    text, spans = parse_markup(marked)
    if noisy:
        end = rng.choice(ENDINGS)
        if end and not text.endswith(("?", ".", "!")):
            text += end
        roll = rng.random()
        if roll < 0.2:
            text = text.lower()
        elif roll < 0.215:
            text = text.upper()
    return text, spans


def generate_intent(intent: str, count: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(f"{seed}:{intent}")
    items = templates.INTENT_TEMPLATES.get(intent) or templates.OUT_OF_SCOPE
    examples: list[dict[str, object]] = []
    for _ in range(count):
        index = rng.randrange(len(items))
        text, spans = compose(items[index], rng)
        if intent == "OUT_OF_SCOPE":
            spans = []  # an out-of-scope request carries no values we act on
        examples.append(
            {
                "text": text,
                "intent": intent,
                "spans": [list(s) for s in spans],
                "family": f"{intent}#{index}",
                "role": ("seen", "seen", "seen", "dev", "heldout")[index % 5],
            }
        )
    return examples
