"""Renderers: each returns a piece of annotated text for one kind of value, in a random style.

Styles are the ways real people write the same thing ("GBP 10,000", "£10k", "ten thousand
pounds", "10000 quid"). The label is attached to the exact words that carry the value; the
words around it (the currency sign next to an amount, "by", "for") are separate or unlabelled.
"""

from __future__ import annotations

import calendar
import random
from datetime import date, timedelta

from markup import mark

CURRENCIES: dict[str, dict[str, list[str]]] = {
    "GBP": {"symbols": ["£"], "words": ["pounds", "quid", "pounds sterling"]},
    "USD": {"symbols": ["$"], "words": ["US dollars", "dollars", "USD"]},
    "EUR": {"symbols": ["€"], "words": ["euros", "euro"]},
    "AUD": {"symbols": ["A$"], "words": ["Australian dollars", "AUD dollars"]},
    "CAD": {"symbols": ["C$"], "words": ["Canadian dollars", "CAD dollars"]},
    "MYR": {"symbols": ["RM"], "words": ["ringgit"]},
}
CURRENCY_WEIGHTS = {"GBP": 30, "USD": 20, "AUD": 15, "CAD": 12, "EUR": 13, "MYR": 10}

_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
MONTHS = list(calendar.month_name)[1:]
WEEKDAYS = list(calendar.day_name)
ORDINAL_WORDS = ["first", "second", "third", "fourth", "fifth", "tenth", "fifteenth", "twentieth"]


def number_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + (" " + number_words(rest) if rest else "")
    rest = n % 1000
    return number_words(n // 1000) + " thousand" + (" " + number_words(rest) if rest else "")


def _ordinal(day: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}th" if 10 <= day % 100 <= 20 else f"{day}{suffix}"


def _indian(n: int) -> str:
    digits = str(n)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


def pick_currency(rng: random.Random) -> str:
    return rng.choices(list(CURRENCY_WEIGHTS), weights=list(CURRENCY_WEIGHTS.values()))[0]


def amount_value(rng: random.Random, purpose: str) -> int:
    if purpose == "LIVING":
        return rng.randrange(4, 61) * 50
    return rng.randrange(30, 900) * 50


def _number_text(rng: random.Random, value: int, allow_words: bool = True) -> tuple[str, bool]:
    """The number as written, and whether it already carries a "k" so a unit word may follow."""
    styles = ["comma"] * 6 + ["plain"] * 3 + ["indian"]
    if value % 100 == 0:
        styles += ["k"] * 4
    if allow_words and value % 500 == 0 and value < 100_000:
        styles += ["words"] * 3
    if value % 50 == 0 and rng.random() < 0.1:
        styles += ["decimals"]
    style = rng.choice(styles)
    if style == "plain":
        return str(value), False
    if style == "indian":
        return _indian(value), False
    if style == "k":
        thousands = value / 1000
        return (f"{thousands:g}k" if rng.random() < 0.8 else f"{thousands:g} k"), True
    if style == "words":
        return number_words(value), False
    if style == "decimals":
        return f"{value:,}.00", False
    return f"{value:,}", False


def money(
    rng: random.Random,
    purpose: str,
    *,
    with_currency: float = 0.93,
    value: int | None = None,
    code: str | None = None,
) -> str:
    """An amount with its currency, e.g. "[[£|CURRENCY]][[10,000|AMOUNT]]". Value and code can be
    fixed (the reinforcement-learning simulator needs a parent who keeps saying the same amount)."""
    code = code or pick_currency(rng)
    value = value if value is not None else amount_value(rng, purpose)
    number, _ = _number_text(rng, value)
    amount = mark(number, "AMOUNT")
    if rng.random() > with_currency:
        return amount
    info = CURRENCIES[code]
    style = rng.choice(
        ["code_first"] * 4 + ["code_tight"] + ["symbol"] * 3 + ["code_after"] * 3
        + ["word_after"] * 3 + ["lower_code"] + ["form"]
    )  # fmt: skip
    code_text = code if style != "lower_code" else code.lower()
    if style in ("code_first", "lower_code"):
        return f"{mark(code_text, 'CURRENCY')} {amount}"
    if style == "code_tight":
        return f"{mark(code, 'CURRENCY')}{amount}"
    if style == "symbol":
        return f"{mark(rng.choice(info['symbols']), 'CURRENCY')}{amount}"
    if style == "code_after":
        return f"{amount} {mark(code, 'CURRENCY')}"
    if style == "word_after":
        return f"{amount} {mark(rng.choice(info['words']), 'CURRENCY')}"
    return f"amount {amount} in {mark(code, 'CURRENCY')}"  # "form"


def future_date(rng: random.Random, today: date) -> date:
    return today + timedelta(days=rng.randint(3, 150))


def date_phrase(rng: random.Random, today: date) -> str:
    d = future_date(rng, today)
    month, mon = MONTHS[d.month - 1], MONTHS[d.month - 1][:3]
    style = rng.choice(
        ["dm"] * 6 + ["d_mon"] * 4 + ["m_d"] * 3 + ["d_ord_m"] * 3 + ["d_of_m"] * 2 + ["dmy"] * 2
        + ["slash"] * 3 + ["iso"] * 2 + ["end_of"] * 2 + ["mid"] + ["rel_weeks"] * 2
        + ["rel_days"] + ["weekday"] + ["tomorrow"] + ["bare_day"] + ["ord_word"]
    )  # fmt: skip
    if style == "dm":
        text = f"{d.day} {month}"
    elif style == "d_mon":
        text = f"{d.day} {mon}"
    elif style == "m_d":
        text = f"{mon} {d.day}"
    elif style == "d_ord_m":
        text = f"{_ordinal(d.day)} {month}"
    elif style == "d_of_m":
        text = f"{_ordinal(d.day)} of {month}"
    elif style == "dmy":
        text = f"{d.day} {month} {d.year}"
    elif style == "slash":
        text = f"{d.day:02d}/{d.month:02d}/{d.year}"
    elif style == "iso":
        text = d.isoformat()
    elif style == "end_of":
        text = f"end of {month}"
    elif style == "mid":
        text = f"mid {month}"
    elif style == "rel_weeks":
        n = rng.randint(2, 12)
        text = f"in {n} weeks" if rng.random() < 0.6 else f"in {number_words(n)} weeks"
    elif style == "rel_days":
        text = f"in {rng.randint(5, 60)} days"
    elif style == "weekday":
        text = rng.choice(["next ", "this ", ""]) + rng.choice(WEEKDAYS)
    elif style == "tomorrow":
        text = "tomorrow"
    elif style == "bare_day":
        text = f"the {_ordinal(d.day)}"
    else:
        text = f"{rng.choice(ORDINAL_WORDS)} of {month}"
    return mark(text, "DATE")


def duration(rng: random.Random) -> str:
    n = rng.randint(2, 12)
    style = rng.choice(["digits"] * 5 + ["words"] * 2 + ["year"] * 2 + ["academic"])
    if style == "digits":
        return mark(f"{n} months", "DURATION")
    if style == "words":
        return mark(f"{number_words(n)} months", "DURATION")
    if style == "year":
        return mark(rng.choice(["a year", "one year", "12 months"]), "DURATION")
    return mark("the academic year", "DURATION")


def charge_with(rng: random.Random, code: str) -> str:
    return mark(rng.choice([code, code, code.lower(), code.capitalize()]), "CHARGE")


def charge(rng: random.Random) -> str:
    return charge_with(rng, rng.choice(["OUR", "SHA", "BEN"]))


def purpose(rng: random.Random, kind: str | None = None) -> str:
    kind = kind or rng.choice(["TUITION", "LIVING"])
    if kind == "LIVING":
        words = ["living costs", "living expenses", "rent", "accommodation", "pocket money",
                 "monthly allowance", "food and rent", "groceries", "stipend"]  # fmt: skip
    else:
        words = ["tuition", "tuition fees", "tuition fee", "course fees", "semester fees",
                 "term fees", "fees"]  # fmt: skip
    return mark(rng.choice(words), "PURPOSE")


def provider_with(rng: random.Random, letter: str) -> str:
    style = rng.choice(["Provider {}", "Provider {}", "provider {}", "prov_{}", "{}"])
    text = style.format(letter.lower() if style.startswith("prov_") else letter)
    return mark(text, "PROVIDER")


UNIVERSITIES = [
    "Meridian University", "the University of Exampleton", "Harbour College", "Northgate University",
    "my son's university", "my daughter's university", "the university", "her college",
    "Riverside Institute", "Westbrook University",
]  # fmt: skip
JUNK = [
    "invoice INV-2026-4471", "ref 883201", "student ID STU-5521", "semester 2", "year 3",
    "page 3", "order 12", "my 2 kids", "case 7741", "form 17B", "flat 4B", "batch 2026",
]  # fmt: skip


def date_for(rng: random.Random, d: date) -> str:
    """The given date in one of the absolute written styles (no relative phrases)."""
    month, mon = MONTHS[d.month - 1], MONTHS[d.month - 1][:3]
    style = rng.choice(["dm"] * 4 + ["d_mon"] * 3 + ["m_d"] * 2 + ["d_ord_m"] * 2 + ["d_of_m"]
                       + ["dmy"] + ["slash"] * 2 + ["iso"])  # fmt: skip
    text = {
        "dm": f"{d.day} {month}", "d_mon": f"{d.day} {mon}", "m_d": f"{mon} {d.day}",
        "d_ord_m": f"{_ordinal(d.day)} {month}", "d_of_m": f"{_ordinal(d.day)} of {month}",
        "dmy": f"{d.day} {month} {d.year}", "slash": f"{d.day:02d}/{d.month:02d}/{d.year}",
        "iso": d.isoformat(),
    }[style]
    return mark(text, "DATE")


def months_for(rng: random.Random, n: int) -> str:
    """A period of n months as people write it."""
    if n == 12 and rng.random() < 0.4:
        return mark(rng.choice(["a year", "one year", "the academic year"]), "DURATION")
    return mark(rng.choice([f"{n} months", f"{n} months", f"{number_words(n)} months"]), "DURATION")
