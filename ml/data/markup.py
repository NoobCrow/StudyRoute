"""Inline annotation: "pay [[10k|AMOUNT]] [[quid|CURRENCY]] by [[28 Oct|DATE]]".

The same notation is used by the generator's templates and by the hand-written test set, so a
span always comes from the text itself and its character offsets are exact.
"""

from __future__ import annotations

import re

_SPAN = re.compile(r"\[\[(.+?)\|([A-Z]+)\]\]")


def mark(text: str, label: str) -> str:
    return f"[[{text}|{label}]]"


def parse_markup(marked: str) -> tuple[str, list[tuple[int, int, str]]]:
    """Return the clean text and its spans as (start, end, label)."""
    clean: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    length = 0
    for match in _SPAN.finditer(marked):
        before = marked[cursor : match.start()]
        clean.append(before)
        length += len(before)
        inner = match.group(1)
        spans.append((length, length + len(inner), match.group(2)))
        clean.append(inner)
        length += len(inner)
        cursor = match.end()
    clean.append(marked[cursor:])
    return "".join(clean), spans
