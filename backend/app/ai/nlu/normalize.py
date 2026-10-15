"""Turn a span of the person's own words into a typed value, with plain deterministic code.

The reader model only says WHICH words carry an amount, a currency, a date... This module says
WHAT they mean. If a span cannot be understood it returns None and the assistant asks again; it
never guesses. Amounts go through Decimal and integer minor units, never a float.

Beyond what ``request_parser`` understands, this reads number words ("ten thousand"), suffixes
("10k", "1.5 lakh", "2 crore", "3m"), slang ("quid", "grand"), Indian digit grouping
("1,00,000"), ordinal words ("first of December"), weekdays, "end of October", "mid November",
"in three weeks" and "tomorrow".
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Collection
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.ai.request_parser import MAX_MINOR, _find_date, _is_written_as_code
from app.engine.money import CURRENCY_EXPONENTS, Money

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip
_SCALES = {
    "k": 1_000, "thousand": 1_000, "grand": 1_000, "lakh": 100_000, "lakhs": 100_000,
    "lac": 100_000, "lacs": 100_000, "crore": 10_000_000, "crores": 10_000_000,
    "cr": 10_000_000, "m": 1_000_000, "mn": 1_000_000, "million": 1_000_000,
}  # fmt: skip
_FILLER = frozenset({"a", "an", "and", "of", "about", "around", "approximately", "roughly"})
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")
_SYMBOLS = "£€$৳"
# 1,000 / 10,000 / 1,000,000 and the South Asian 1,00,000 / 12,50,000 / 1,00,00,000
_GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3}")


def _small_number(token: str) -> Decimal | None:
    if token in _UNITS:
        return Decimal(_UNITS[token])
    return None


def parse_amount(text: str) -> Decimal | None:
    """ "10,000", "10k", "ten thousand", "1.5 lakh", "1,00,000" -> a Decimal, else None."""
    cleaned = text.strip().lower()
    for run in re.findall(r"\d[\d,]*\d", cleaned):
        if "," in run and not _GROUPED.fullmatch(run):
            return None  # "1,5" could be 1.5 or 15: do not guess
    cleaned = cleaned.replace(",", "")
    for symbol in _SYMBOLS:
        cleaned = cleaned.replace(symbol, " ")
    tokens = _TOKEN.findall(cleaned)
    if not tokens:
        return None
    total = Decimal(0)
    current = Decimal(0)
    seen_number = False
    previous_digits: str | None = None
    for index, word in enumerate(tokens):
        if word[0].isdigit():
            if previous_digits is not None:  # "10 000": a space used as a thousands separator
                if len(word) != 3 or "." in word or "." in previous_digits:
                    return None
                current = current * 1000 + Decimal(word)
                previous_digits = None
                continue
            current += Decimal(word)
            previous_digits = word
            seen_number = True
            continue
        previous_digits = None
        following = tokens[index + 1] if index + 1 < len(tokens) else ""
        if word in ("a", "an") and (following in _SCALES or following == "hundred"):
            current += 1  # "a thousand", "a hundred"
            seen_number = True
            continue
        if word in _FILLER:
            continue
        if word in _SCALES:
            if not seen_number:
                return None  # a bare "k" or "thousand" is not an amount
            total += (current if current else Decimal(1)) * _SCALES[word]
            current = Decimal(0)
            continue
        if word == "hundred":
            current = (current if current else Decimal(1)) * 100
            seen_number = True
            continue
        small = _small_number(word)
        if small is None:
            return None
        current += small
        seen_number = True
    value = total + current
    return value if seen_number and value > 0 else None


def to_minor(value: Decimal, currency: str) -> int | None:
    """Integer minor units for ``value`` in ``currency``, or None if it is not a sane amount."""
    if currency not in CURRENCY_EXPONENTS:
        return None
    try:
        minor = Money.from_major(value, currency).amount_minor
    except (TypeError, ValueError, ArithmeticError, InvalidOperation):
        return None
    return minor if 0 < minor <= MAX_MINOR else None


# --- currency -----------------------------------------------------------------------------------
_CURRENCY_SYMBOLS = {
    "£": "GBP", "€": "EUR", "$": "USD", "৳": "BDT", "rm": "MYR", "a$": "AUD", "au$": "AUD",
    "c$": "CAD", "ca$": "CAD", "us$": "USD",
}  # fmt: skip
_CURRENCY_WORDS = {
    "pound": "GBP", "pounds": "GBP", "sterling": "GBP", "quid": "GBP", "pound sterling": "GBP",
    "pounds sterling": "GBP", "euro": "EUR",
    "euros": "EUR", "dollar": "USD", "dollars": "USD", "bucks": "USD", "us dollar": "USD",
    "us dollars": "USD", "american dollars": "USD", "australian dollar": "AUD",
    "australian dollars": "AUD", "aussie dollars": "AUD", "canadian dollar": "CAD",
    "canadian dollars": "CAD", "ringgit": "MYR", "taka": "BDT", "tk": "BDT", "yen": "JPY",
    "rupee": "INR", "rupees": "INR", "won": "KRW", "baht": "THB", "lira": "TRY",
    "franc": "CHF", "francs": "CHF", "rand": "ZAR", "dirham": "AED", "dirhams": "AED",
    "riyal": "SAR", "yuan": "CNY", "rmb": "CNY", "renminbi": "CNY", "zloty": "PLN",
    "krona": "SEK", "kronor": "SEK", "krone": "NOK", "kroner": "NOK",
}  # fmt: skip


def parse_currency(text: str, supported: Collection[str]) -> str | None:
    """ "GBP", "£", "pounds", "quid", "Australian dollars" -> an ISO code the sandbox serves."""
    raw = text.strip()
    if not raw:
        return None
    lowered = " ".join(raw.lower().replace(".", "").split())
    code: str | None = None
    if len(raw) == 3 and raw.isalpha():
        upper = raw.upper()
        if upper in supported and _is_written_as_code(raw):
            code = upper
    if code is None:
        code = _CURRENCY_SYMBOLS.get(lowered) or _CURRENCY_WORDS.get(lowered)
    if code is None and lowered.endswith("s") and lowered[:-1] in _CURRENCY_WORDS:
        code = _CURRENCY_WORDS[lowered[:-1]]
    if code is None:
        parts = lowered.split()
        if len(parts) == 2 and parts[1] in ("dollar", "dollars") and parts[0].upper() in supported:
            code = parts[0].upper()  # "AUD dollars", "cad dollars"
    if code is None:
        return None
    return code if code in supported and code in CURRENCY_EXPONENTS else None


# --- dates --------------------------------------------------------------------------------------
_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december",
)  # fmt: skip
_MONTH_RE = "|".join(m[:3] for m in _MONTH_NAMES)
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
    "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20, "twenty first": 21, "twenty-first": 21,
    "twenty second": 22, "twenty-second": 22, "twenty third": 23, "twenty-third": 23,
    "twenty fourth": 24, "twenty-fourth": 24, "twenty fifth": 25, "twenty-fifth": 25,
    "twenty sixth": 26, "twenty-sixth": 26, "twenty seventh": 27, "twenty-seventh": 27,
    "twenty eighth": 28, "twenty-eighth": 28, "twenty ninth": 29, "twenty-ninth": 29,
    "thirtieth": 30, "thirty first": 31, "thirty-first": 31,
}  # fmt: skip
_ORDINAL_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(w) for w in _ORDINAL_WORDS), key=len, reverse=True))
    + rf")\b(?=\s+(?:of\s+)?(?:{_MONTH_RE}|next\s+month|this\s+month))",
    re.I,
)  # fmt: skip
_END_OF = re.compile(rf"\b(?:end|last\s+day)\s+of\s+({_MONTH_RE})[a-z]*", re.I)
_MID = re.compile(rf"\b(?:mid|middle\s+of)[\s-]+({_MONTH_RE})[a-z]*", re.I)
_DAY_OF_RELATIVE_MONTH = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+of\s+(next|this)\s+month\b", re.I
)
_RELATIVE = re.compile(
    r"\bin\s+(an?|[a-z-]+|\d{1,3})\s+(day|week|fortnight|month)s?\b", re.I
)  # fmt: skip
_WEEKDAY = re.compile(
    r"\b(?:(this|next|coming)\s+)?(" + "|".join(_WEEKDAYS) + r")\b", re.I
)  # fmt: skip
_BARE_DAY = re.compile(r"^\s*(?:by\s+)?(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)\s*$", re.I)


def _add_months(start: date, months: int) -> date:
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _count(token: str) -> int | None:
    if token.lower() in ("a", "an"):
        return 1
    if token.isdigit():
        return int(token)
    value = parse_amount(token.replace("-", " "))
    return int(value) if value is not None and value == int(value) else None


def _month_index(name: str) -> int:
    return [m[:3] for m in _MONTH_NAMES].index(name[:3].lower()) + 1


def _next_on_or_after(month: int, day: int, today: date) -> date | None:
    for year in (today.year, today.year + 1):
        try:
            found = date(year, month, day)
        except ValueError:
            return None
        if found >= today:
            return found
    return None


def _weekday_date(match: re.Match[str], today: date) -> date:
    target = _WEEKDAYS.index(match.group(2).lower())
    ahead = (target - today.weekday()) % 7
    if (match.group(1) or "").lower() == "next":  # the same weekday of next calendar week
        monday_next_week = today + timedelta(days=7 - today.weekday())
        return monday_next_week + timedelta(days=target)
    return today + timedelta(days=ahead)


def parse_date(text: str, today: date) -> date | None:
    """A due date from the person's words, or None when it cannot be read exactly."""
    phrase = _ORDINAL_WORD_RE.sub(lambda m: f"{_ORDINAL_WORDS[m.group(1).lower()]}", text.strip())
    lowered = phrase.lower()
    if re.search(r"\bday\s+after\s+tomorrow\b", lowered):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", lowered):
        return today
    if (m := _END_OF.search(phrase)) is not None:
        month = _month_index(m.group(1))
        return _next_on_or_after(month, calendar.monthrange(today.year, month)[1], today) or (
            date(today.year + 1, month, calendar.monthrange(today.year + 1, month)[1])
        )
    if (m := _MID.search(phrase)) is not None:
        return _next_on_or_after(_month_index(m.group(1)), 15, today)
    if (m := _DAY_OF_RELATIVE_MONTH.search(phrase)) is not None:
        base = _add_months(today.replace(day=1), 1 if m.group(2).lower() == "next" else 0)
        try:
            return base.replace(day=int(m.group(1)))
        except ValueError:
            return None
    if (m := _RELATIVE.search(phrase)) is not None:
        count = _count(m.group(1))
        unit = m.group(2).lower()
        if count is None or not 0 < count <= 365:
            return None
        if unit == "month":
            return _add_months(today, count)
        return today + timedelta(days={"day": 1, "week": 7, "fortnight": 14}[unit] * count)
    found = _find_date(phrase, today)
    if found is not None:
        return found
    if (m := _WEEKDAY.search(phrase)) is not None:
        return _weekday_date(m, today)
    if (m := _BARE_DAY.match(phrase)) is not None:
        day = int(m.group(1))
        for offset in (0, 1):
            base = _add_months(today.replace(day=1), offset)
            try:
                candidate = base.replace(day=day)
            except ValueError:
                continue
            if candidate >= today:
                return candidate
    return None


# --- the rest -----------------------------------------------------------------------------------
_DURATION = re.compile(r"(\d{1,2}|[a-z-]+)\s*[- ]?\s*(month|year|yr)s?\b", re.I)
_A_YEAR = re.compile(
    r"\b(?:a|one|the|per)\s+(?:academic\s+)?year\b|\bacademic\s+year\b|annual", re.I
)


def parse_duration_months(text: str) -> int | None:
    """ "9 months", "nine months", "a year", "the academic year" -> a number of months."""
    if (m := _DURATION.search(text)) is not None:
        count = _count(m.group(1))
        if count is not None:
            months = count * (12 if m.group(2).lower() in ("year", "yr") else 1)
            return months if 1 <= months <= 60 else None
    return 12 if _A_YEAR.search(text) else None


def parse_charge(text: str) -> str | None:
    found = re.search(r"\b(our|sha|ben)\b", text, re.I)
    return found.group(1).upper() if found else None


def parse_purpose(text: str) -> str | None:
    living = r"living|\brent\b|food|stipend|allowance|accommodation|groceries|pocket"
    if re.search(living, text, re.I):
        return "LIVING"
    if re.search(r"tuition|\bfees?\b|course|semester|term", text, re.I):
        return "TUITION"
    return None


def parse_provider(text: str) -> str | None:
    found = re.fullmatch(r"(?:prov_|provider\s*)?([abc])", text.strip(), re.I)
    return f"prov_{found.group(1).lower()}" if found else None
