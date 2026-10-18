"""Number guard (blueprint 14.2 step 6): every number in a reply must come from the engine.

The model may only repeat figures that appear in the FACTS list. Anything else is treated as
an invented number and the reply is discarded.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Digits that are not glued to letters, underscores or a leading dot. "fact_17", "prov_b2"
# and "7c1d-..." are identifiers, not figures; "25,300.00", "1.58%" and "2026-10-28" are.
_NUMBER = re.compile(r"(?<![A-Za-z0-9_.])\d[\d,]*(?:\.\d+)?(?![A-Za-z_])")


def numbers_in(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    for match in _NUMBER.finditer(text):
        cleaned = match.group().replace(",", "")
        try:
            found.append(Decimal(cleaned))
        except InvalidOperation:
            continue
    return found


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    offending: tuple[str, ...]


def allowed_numbers(values: Iterable[str]) -> set[Decimal]:
    allowed: set[Decimal] = set()
    for value in values:
        allowed.update(numbers_in(value))
    return allowed


def check_numbers(reply: str, allowed: set[Decimal]) -> GuardResult:
    """Fail if the reply contains a number that is not in `allowed` (compared by value)."""
    bad = [str(n.normalize()) for n in numbers_in(reply) if n not in allowed]
    return GuardResult(not bad, tuple(dict.fromkeys(bad)))
