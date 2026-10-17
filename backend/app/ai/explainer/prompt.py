"""The compact input the small trained explainer reads.

The assistant builds one long prompt for any model (`app.ai.prompt.build_prompt`) and, for a model
that rewrites the engine's answer, appends the engine's draft. A cloud model can read all of it; a
77-million-parameter model does not need to. It needs the question and the draft: the draft
already holds every correct figure, so the model never has to find, select or compute one. This
keeps only those, with the policy flags. Training and the runtime use this one function, so what
the model learned on is exactly what it is shown."""

from __future__ import annotations

import re

MAX_QUESTION_CHARS = 300
MAX_DRAFT_CHARS = 2000
DRAFT_MARKER = "ENGINE DRAFT (every figure in it is correct; keep them exactly):\n"

_FLAGS = re.compile(r"^Policy flags on the user message: (?P<flags>.+)$", re.M)
_QUESTION = re.compile(r"<<<\n(?P<text>.*?)\n>>>", re.S)


def question_of(user_prompt: str) -> str:
    match = _QUESTION.search(user_prompt)
    return (match.group("text") if match else "").strip().replace("\n", " ")


def draft_of(user_prompt: str) -> str:
    """The engine's draft answer at the end of the prompt, or an empty string."""
    _, found, rest = user_prompt.partition(DRAFT_MARKER)
    return rest.split("\n\nYour previous reply was rejected", 1)[0].strip() if found else ""


def compact_input(user_prompt: str) -> str:
    """`question: ... | flags: ... | draft: ...`"""
    flags = _FLAGS.search(user_prompt)
    return (
        "rewrite the draft to answer the question"
        f" | question: {question_of(user_prompt)[:MAX_QUESTION_CHARS]}"
        f" | flags: {flags.group('flags') if flags else 'none'}"
        f" | draft: {draft_of(user_prompt)[:MAX_DRAFT_CHARS]}"
    )
