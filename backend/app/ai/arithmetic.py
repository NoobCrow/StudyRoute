"""Small bounded read-only calculator, not payment/FX arithmetic and never eval()."""

from __future__ import annotations

import re
from decimal import Decimal, localcontext
from fractions import Fraction

_PATTERN = re.compile(
    r"\s*([+-]?\d{1,9}(?:\.\d{1,4})?)\s*([+*/\u00d7÷\u2212-])\s*([+-]?\d{1,9}(?:\.\d{1,4})?)\s*(?:=\s*)?[?\uff1f]*\s*"
)
_TRANSLATION = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def calculate(text: str) -> str | None:
    match = _PATTERN.fullmatch(text.translate(_TRANSLATION))
    if not match:
        return None
    left, operator, right = match.groups()
    a, b = Decimal(left), Decimal(right)
    operator = operator.translate(str.maketrans({"\u00d7": "*", "÷": "/", "\u2212": "-"}))
    if operator == "/" and not b:
        return None
    if operator == "/":
        denominator = (Fraction(a) / Fraction(b)).denominator
        for factor in (2, 5):
            while denominator % factor == 0:
                denominator //= factor
        if denominator != 1:
            return None
    with localcontext() as context:
        # At most 13 coefficient digits per input; 64 covers every terminating result.
        context.prec = 64
        result = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b}[
            operator
        ]()
    return f"{left} {operator} {right} = {format(result, 'f')}"
