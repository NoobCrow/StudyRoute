"""Read a place and a monthly budget out of a student's question. Plain code: no model, no guessing.

The place is a city or a country the config knows; the budget is an amount in taka, written as
"BDT 200,000", "150000 taka", "Tk 90,000", "2 lakh" or "a budget of 120000". A number that does
not look like a month's money in taka (a year, a small count) is never taken for a budget.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.domain.rules import Rules
from app.domain.student_guide import COST_PREFIX
from app.engine.money import Money

MIN_BUDGET_BDT = Decimal(1_000)
MAX_BUDGET_BDT = Decimal(10_000_000)
_ALIASES = {
    "uk": "GB",
    "u.k.": "GB",
    "britain": "GB",
    "great britain": "GB",
    "england": "GB",
    "scotland": "GB",
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "america": "US",
}
_NUMBER = r"(\d+(?:,\d{2,3})*(?:\.\d+)?)"
_UNIT = r"(?:\s*(lakhs?|lacs?|k)(?![A-Za-z]))?"
_MARK = "(?<![A-Za-z])(?:bdt|tk\\.?|taka|৳)(?![A-Za-z])"
_BUDGETS = (
    re.compile(_MARK + r"\s*" + _NUMBER + _UNIT, re.I),  # BDT 200,000
    re.compile(_NUMBER + _UNIT + r"\s*" + _MARK, re.I),  # 150000 taka, 2 lakh taka
    re.compile(r"(?<![\w.])" + _NUMBER + r"\s*(lakhs?|lacs?)(?![A-Za-z])", re.I),  # 1.5 lakh
    re.compile(r"\bbudget\s+(?:of|is|about|around)?\s*" + _NUMBER + _UNIT, re.I),
)
_STUDIO = re.compile(
    r"\bstudio\b|\bown\s+(?:flat|apartment|room|place)\b|\bprivate\s+(?:room|flat|apartment)\b"
    r"|\blive\s+alone\b|\bby\s+myself\b",
    re.I,
)
_MULTIPLIER = {"k": Decimal(1_000), "lakh": Decimal(100_000), "lac": Decimal(100_000)}


@dataclass(frozen=True)
class StudentTopic:
    city: str | None
    country: str | None
    budget_bdt: Money | None
    housing: str


def _earliest(text: str, names: dict[str, str]) -> str | None:
    """The value for the name that appears first in the text (whole words, any case)."""
    best: tuple[int, str] | None = None
    for name, value in names.items():
        pattern = r"(?<![A-Za-z])" + r"\s+".join(map(re.escape, name.split())) + r"(?![A-Za-z])"
        found = re.search(pattern, text, re.I)
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), value)
    return best[1] if best else None


def _budget(text: str) -> Money | None:
    for pattern in _BUDGETS:
        for found in pattern.finditer(text):
            unit = found.group(2) or ""
            multiplier = _MULTIPLIER.get(unit.lower().rstrip("s"), Decimal(1))
            amount = Decimal(found.group(1).replace(",", "")) * multiplier
            if MIN_BUDGET_BDT <= amount <= MAX_BUDGET_BDT:
                return Money.from_major(amount, "BDT")
    return None


def parse_student_topic(text: str, rules: Rules) -> StudentTopic:
    cities: dict[str, str] = {}
    for country, record in rules.records_with_prefix(COST_PREFIX).items():
        for city in record.value["cities"]:
            cities[str(city)] = country
    city = _earliest(text, {name: name for name in cities})
    country = cities[city] if city else None
    if country is None:
        names = {c.name: code for code, c in rules.corridors().items()}
        names.update(_ALIASES)
        country = _earliest(text, names)
    return StudentTopic(
        city=city,
        country=country,
        budget_bdt=_budget(text),
        housing="studio" if _STUDIO.search(text) else "shared",
    )
