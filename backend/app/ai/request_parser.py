"""Read a payment request from plain text, without a model.

"I need to pay GBP 10,000 tuition by 28 October" becomes an amount in minor units, a currency, a
due date, a purpose and a charge code. This is deterministic code: nothing is guessed, amounts go
through Decimal (never a float), and anything that is missing or impossible stays None so the
assistant can ask instead of inventing. The parser only reads; the engine does every calculation.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.engine.money import CURRENCY_EXPONENTS, Money

MAX_MINOR = 10**10
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_AMOUNT = r"(\d[\d,]*(?:\.\d+)?)"
_SYMBOLS = {"£": "GBP", "€": "EUR"}
_WORDS = {
    "pound": "GBP", "pounds": "GBP", "euro": "EUR", "euros": "EUR", "ringgit": "MYR",
    "us dollars": "USD", "us dollar": "USD", "australian dollars": "AUD",
    "canadian dollars": "CAD",
}  # fmt: skip

_CODE_AFTER = re.compile(rf"{_AMOUNT}\s*(k)?\s*([A-Za-z]{{3}})\b", re.I)
_CODE_FIRST_PLAIN = re.compile(rf"\b([A-Za-z]{{3}})\s*{_AMOUNT}\s*(k)?\b", re.I)
_SYMBOL = re.compile(rf"([£€])\s*{_AMOUNT}\s*(k)?", re.I)
_WORD_NAMES = r"us dollars?|australian dollars?|canadian dollars?|pounds?|euros?|ringgit"
_WORD = re.compile(rf"{_AMOUNT}\s*(k)?\s*({_WORD_NAMES})\b", re.I)

_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH}(?:,?\s+(\d{{4}}))?(?!\d)", re.I
)
_MONTH_DAY = re.compile(rf"\b{_MONTH}\s+(\d{{1,2}})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", re.I)
_NUMERIC = re.compile(r"\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b")
_RELATIVE = re.compile(r"\bin\s+(\d{1,3})\s+(day|week)s?\b", re.I)

_PER_MONTH = re.compile(r"\b(?:a|per|each|every)\s+month\b|\bmonthly\b|/\s*month", re.I)
_MONTHS_COUNT = re.compile(r"\b(?:for\s+)?(\d{1,2})[\s-]+months?\b", re.I)
_A_YEAR = re.compile(
    r"\b(?:a|one|the|per)\s+(?:academic\s+)?year\b|\bacademic\s+year\b|\bannual", re.I
)
_LIVING = re.compile(r"living|\brent\b|food|stipend|allowance|accommodation|groceries", re.I)
_TUITION = re.compile(r"tuition|\bfees?\b", re.I)
_CHARGE_CAPS = re.compile(r"\b(OUR|SHA|BEN)\b")
_CHARGE_WORDED = re.compile(
    r"\b(our|sha|ben)\s+charges?\b|\bcharges?\s+(?:code\s+)?(our|sha|ben)\b", re.I
)


@dataclass(frozen=True)
class ParsedRequest:
    amount_minor: int | None
    currency: str | None
    due_date: date | None
    purpose: str
    charge_code: str
    months: int | None
    per_month: bool

    @property
    def has_amount(self) -> bool:
        return self.amount_minor is not None and self.currency is not None


def _to_minor(raw: str, thousands: bool, currency: str) -> int | None:
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    if thousands:
        value *= 1000
    try:
        minor = Money.from_major(value, currency).amount_minor
    except (TypeError, ValueError, ArithmeticError):
        return None
    return minor if 0 < minor <= MAX_MINOR else None


def _find_amount(text: str, currencies: Collection[str]) -> tuple[int, str] | None:
    candidates: list[tuple[int, str, str, bool]] = []  # position, amount, currency, k
    for match in _SYMBOL.finditer(text):
        candidates.append(
            (match.start(), match.group(2), _SYMBOLS[match.group(1)], bool(match.group(3)))
        )
    for match in _WORD.finditer(text):
        candidates.append(
            (match.start(), match.group(1), _WORDS[match.group(3).lower()], bool(match.group(2)))
        )
    for match in _CODE_AFTER.finditer(text):
        code = match.group(3).upper()
        if code in currencies:
            candidates.append((match.start(), match.group(1), code, bool(match.group(2))))
    for match in _CODE_FIRST_PLAIN.finditer(text):
        code = match.group(1).upper()
        if code in currencies:
            candidates.append((match.start(), match.group(2), code, bool(match.group(3))))
    for _, raw, currency, thousands in sorted(candidates):
        if currency not in currencies or currency not in CURRENCY_EXPONENTS:
            continue
        minor = _to_minor(raw, thousands, currency)
        if minor is not None:
            return minor, currency
    return None


def _month_number(token: str) -> int:
    return _MONTHS.index(token[:3].lower()) + 1


def _build(year: int, month: int, day: int, today: date, explicit_year: bool) -> date | None:
    try:
        built = date(year, month, day)
    except ValueError:
        return None
    if not explicit_year and built < today:
        try:
            return date(year + 1, month, day)
        except ValueError:
            return None
    return built


def _find_date(text: str, today: date) -> date | None:
    if (m := _ISO.search(text)) is not None:
        found = _build(int(m.group(1)), int(m.group(2)), int(m.group(3)), today, True)
        if found:
            return found
    if (m := _NUMERIC.search(text)) is not None:  # day/month/year, as written in Bangladesh
        found = _build(int(m.group(3)), int(m.group(2)), int(m.group(1)), today, True)
        if found:
            return found
    if (m := _DAY_MONTH.search(text)) is not None:
        year = int(m.group(3)) if m.group(3) else today.year
        found = _build(year, _month_number(m.group(2)), int(m.group(1)), today, bool(m.group(3)))
        if found:
            return found
    if (m := _MONTH_DAY.search(text)) is not None:
        year = int(m.group(3)) if m.group(3) else today.year
        found = _build(year, _month_number(m.group(1)), int(m.group(2)), today, bool(m.group(3)))
        if found:
            return found
    if (m := _RELATIVE.search(text)) is not None:
        step = 7 if m.group(2).lower() == "week" else 1
        return today + timedelta(days=int(m.group(1)) * step)
    return None


def _find_months(text: str) -> int | None:
    if (m := _MONTHS_COUNT.search(text)) is not None and 1 <= int(m.group(1)) <= 60:
        return int(m.group(1))
    return 12 if _A_YEAR.search(text) else None


def _purpose(text: str, per_month: bool) -> str:
    if _LIVING.search(text):
        return "LIVING"
    if _TUITION.search(text):
        return "TUITION"
    return "LIVING" if per_month else "TUITION"


def _charge_code(text: str) -> str:
    if (m := _CHARGE_CAPS.search(text)) is not None:
        return m.group(1)
    if (m := _CHARGE_WORDED.search(text)) is not None:
        return next(g for g in m.groups() if g).upper()
    return "OUR"


def parse_request(message: str, currencies: Collection[str], today: date) -> ParsedRequest:
    """Read what the message says. Missing or impossible parts stay None."""
    text = message.strip()
    found = _find_amount(text, currencies)
    per_month = _PER_MONTH.search(text) is not None
    return ParsedRequest(
        amount_minor=found[0] if found else None,
        currency=found[1] if found else None,
        due_date=_find_date(text, today),
        purpose=_purpose(text, per_month),
        charge_code=_charge_code(text),
        months=_find_months(text),
        per_month=per_month,
    )
