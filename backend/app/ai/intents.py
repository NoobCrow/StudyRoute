"""Rule-based intent detection for template mode (no model needed)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from app.ai.request_parser import ParsedRequest
from app.domain.stress import DEFAULT_DROPS, MAX_DROP, MAX_SCENARIOS


class Intent(StrEnum):
    DRAFT = "DRAFT"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    COMPARE = "COMPARE"
    CHARGES = "CHARGES"
    DEADLINE = "DEADLINE"
    CHECKLIST = "CHECKLIST"
    LIMITS = "LIMITS"
    KYC = "KYC"
    STATUS = "STATUS"
    HELP = "HELP"
    PLAN = "PLAN"  # a task: read a payment request, quote it, prepare the plan
    CADENCE = "CADENCE"  # a task: compare monthly, quarterly, termly and upfront sending
    STRESS = "STRESS"  # a question: what if the taka weakened before the money is sent
    COSTS = (
        "COSTS"  # a question: rent and the cost of a month in a city, or which city fits a budget
    )
    ARRIVAL = "ARRIVAL"  # a question: what to do before flying and in the first weeks abroad


_STRESS = re.compile(
    r"stress[- ]?test|currency[- ]?(?:drop|crash|shock|risk)"
    r"|\btaka\s+(?:drop|drops|dropped|fall|falls|fell|weak\w*|depreciat\w*|lose[sd]?|slides?|crash\w*)"
    r"|\b(?:drop|fall|dip|slide|weakening|depreciation)\s+(?:in|of)\s+(?:the\s+)?(?:taka|bdt|currency|rate)"
    r"|what\s+if\s+(?:the\s+)?(?:taka|bdt|rate|pound|gbp|dollar|usd|euro|eur|exchange)"
    r"|if\s+(?:the\s+)?(?:taka|bdt|rate)\s+(?:drops?|falls?|weakens?|depreciat\w+|loses?|slides?"
    r"|changes?|moves?|goes)",
    re.I,
)
_DROP_PCT = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:%|percent|per\s+cent)", re.I)


def stress_drops(message: str) -> tuple[Decimal, ...]:
    """Percentages the person named ("what if the taka drops 12%"), on top of the usual four."""
    named = {Decimal(m.group(1)) for m in _DROP_PCT.finditer(message)}
    named = {v for v in named if Decimal(1) <= v <= MAX_DROP}
    merged = sorted(set(DEFAULT_DROPS) | named)
    while len(merged) > MAX_SCENARIOS:  # keep the named ones, drop the usual ones that fit least
        removable = [v for v in merged if v not in named]
        merged.remove(removable[-1] if removable else merged[-1])
    return tuple(merged)


_COSTS = re.compile(
    r"cost\s+of\s+living|\bliving\s+(?:costs?|expenses?)\s+(?:in|for|at)\s+[a-z]"
    r"|\bcosts?\s+(?:to|of)\s+(?:live|living|study|studying)\b"
    r"|\b(?:what|how\s+much)\s+(?:is|are|does|do)\s+(?:the\s+|an?\s+|average\s+|typical\s+|monthly\s+)*(?:rents?|accommodation|housing)\b"
    r"|\b(?:is|are)\s+(?:the\s+)?rents?\s+(?:in|at|near|for)\b|\b(?:average|typical)\s+rents?\b"
    r"|\brent\s+(?:prices?|costs?|levels?)\b"
    r"|\bwhich\s+(?:city|cities|towns?|countr(?:y|ies)|places?)\b.{0,60}"
    r"\b(?:fits?|afford\w*|cheap\w*|budget|costs?|rent|live|study|studying)\b"
    r"|\b(?:cheap\w*|afford\w*|budget)\b.{0,40}\b(?:city|cities|countr(?:y|ies)|towns?|places?)\b"
    r"|\bcan\s+i\s+afford\b|\bstudent\s+budget\b",
    re.I,
)
_ARRIVAL = re.compile(
    r"when\s+i\s+(?:arrive|land|get\s+there|reach|get\s+to)\b|(?:after|once)\s+(?:i\s+)?(?:arrive|land)\b"
    r"|\bjust\s+arrived\s+(?:abroad|in\s+the\s+(?:uk|usa|country|city))\b"
    r"|first\s+(?:weeks?|months?|few\s+days|days)\b.{0,20}\b(?:abroad|there|in|overseas)\b"
    r"|settl(?:e|ing)\s+in\b|before\s+(?:i|we|you)\s+(?:fly|leave|travel|go\s+abroad|depart)\b"
    r"|arrival\s+(?:guide|checklist|steps|help|tips|list)\b|\bopen\s+(?:a\s+)?student\s+bank\s+account\b|local\s+sim\b"
    r"|moving\s+abroad|new\s+(?:to|in)\s+(?:the\s+)?(?:country|city|uk|usa)\b",
    re.I,
)
# A message that asks to pay, send, settle or plan money is a payment request, whatever else it says
# ("settle the rent bill" is not a question about rent), so it is never a student question.
_PAYING = re.compile(
    r"\b(?:pay|paying|paid|payments?|send|sending|transfers?|transferring|settle(?!\s+in\b)|remit\w*|bills?|invoices?"
    r"|quotes?|plan|planning|due|instal+ments?|lump\s+sum)\b",
    re.I,
)


def student_question(message: str) -> Intent | None:
    """ARRIVAL or COSTS when the message is a question about a student's life abroad, else None."""
    if _PAYING.search(message):
        return None
    if _ARRIVAL.search(message):
        return Intent.ARRIVAL
    if _COSTS.search(message):
        return Intent.COSTS
    return None


_RULES: list[tuple[Intent, re.Pattern[str]]] = [
    (Intent.STRESS, _STRESS),
    (
        Intent.DRAFT,
        re.compile(
            r"\b(?:create|make|start|prepare|open|set\s+up)\b.{0,30}\bdraft\b|\b(?:go|proceed)\s+with\s+provider\b|\bchoose\s+provider\b",
            re.I,
        ),
    ),
    (
        Intent.REQUEST_APPROVAL,
        re.compile(
            r"request(?:ing)?\s+(?:an\s+)?approval|ask\s+for\s+approval|for\s+approval\b", re.I
        ),
    ),
    (
        Intent.CHARGES,
        re.compile(
            r"\b(?:our|sha|ben)\b|charge\s*codes?|\bcharges\b|short.?paid|shortfall|short\s+payment|intermediary|lifting\s+fee",
            re.I,
        ),
    ),
    (
        Intent.DEADLINE,
        re.compile(
            r"deadline|due\s+date|send\s+by|\blatest\b|when\s+(?:should|do|can|must|will)|how\s+(?:long|early)|cut-?off|holiday|weekend|settlement\s+time|how\s+many\s+days",
            re.I,
        ),
    ),
    (
        Intent.CHECKLIST,
        re.compile(
            r"document|checklist|paperwork|\bpapers\b|what\s+do\s+i\s+need|what\s+to\s+bring|\bforms?\b",
            re.I,
        ),
    ),
    (
        Intent.LIMITS,
        re.compile(
            r"\blimits?\b|\bcaps?\b|\ballowed\b|how\s+much\s+can|quota|living\s+expense|per\s+month|maximum",
            re.I,
        ),
    ),
    (Intent.KYC, re.compile(r"\bkyc\b|\bverif(?:y|ied|ication)\b|identity", re.I)),
    (
        Intent.STATUS,
        re.compile(
            r"\bstatus\b|where\s+is|tracker|\btrack\b|\buetr\b|settled|delivered|\barrive|"
            r"bank\s+(?:check|review)|on\s+hold|held\s+up|bank\s+(?:ask|take|say)|"
            r"risk\s+score|how\s+risky|any\s+warning",
            re.I,
        ),
    ),
    (
        Intent.COMPARE,
        re.compile(
            r"cheap|compare|\bbetter\b|\bbest\b|which\s+provider|\brank|\bcost|\bfees?\b|margin|why\s+is|expensive|\bprice|\brate\b",
            re.I,
        ),
    ),
]

_PROVIDER = re.compile(r"\bprov_([a-z])\b|\bprovider\s+([a-z])\b|(?<!^)(?<![.!?]\s)\b([A-C])\b")


def classify(message: str) -> Intent:
    if _STRESS.search(message):
        return Intent.STRESS
    if (student := student_question(message)) is not None:
        return student
    for intent, pattern in _RULES:
        if pattern.search(message):
            return intent
    return Intent.HELP


def mentioned_providers(message: str, provider_ids: Sequence[str]) -> list[str]:
    """Provider ids named in the message ("Provider B", "prov_b", or a bare capital B), in order."""
    found: list[str] = []
    for match in _PROVIDER.finditer(message.strip()):
        letter = next(g for g in match.groups() if g)
        provider_id = f"prov_{letter.lower()}"
        if provider_id in provider_ids and provider_id not in found:
            found.append(provider_id)
    return found


# --- tasks -------------------------------------------------------------------------------------
_CADENCE_WORDS = re.compile(
    r"how\s+often|monthly\s+(?:vs|or|versus)|\bquarterly\b|instal+ments?|\bsplit\b|in\s+parts"
    r"|every\s+(?:three|six|\d+)\s+months|per\s+(?:term|semester)|cheapest\s+way\s+to\s+send"
    r"|send\s+monthly|lump\s+sum|all\s+at\s+once|once\s+a\s+(?:term|semester|year)",
    re.I,
)
_CADENCE_HINT = re.compile(r"cheap|save|best|compare|which|worth", re.I)
_PLAN_ANY = re.compile(
    r"\bplan\b|\bprepare\b|set\s+up\s+a\s+payment|help\s+me\s+pay"
    r"|i\s+(?:need|want|have|would\s+like)\s+to\s+(?:pay|send|transfer)|get\s+me\s+a\s+quote"
    r"|how\s+much\s+(?:will|would|does|do)\b.{0,30}\b(?:cost|send|pay)",
    re.I,
)
_PLAN_OPEN = re.compile(r"tuition|\bfees?\b|\bpay\b|\bsend\b|\btransfer\b|\bremit|\bquote\b", re.I)
_PLAN_STRONG = re.compile(
    r"help\s+me\s+pay|i\s+(?:need|want|would\s+like)\s+to\s+pay"
    r"|plan\s+(?:my|a|the)\s+(?:tuition\s+)?payment|set\s+up\s+a\s+payment",
    re.I,
)
_NOT_A_PLAN = re.compile(
    r"\blimits?\b|\bcaps?\b|\ballowed\b|\blegal|\blawful|\bpermitted\b|\bkyc\b", re.I
)


def choose_intent(message: str, parsed: ParsedRequest, *, has_context: bool) -> Intent:
    """Pick the task for a message, or fall back to the plain question classifier.

    A task is only started when the message really asks for one. An amount alone, a question
    about limits or legality, or a question about a quote that is already open never creates
    a new quote.
    """
    if _STRESS.search(message):
        return Intent.STRESS  # a what-if about the rate never starts a new quote
    if (student := student_question(message)) is not None:
        return student  # "which city fits BDT 200,000" is a question, not a send plan
    if _NOT_A_PLAN.search(message):
        return classify(message)
    if parsed.has_amount:
        asks_cadence = _CADENCE_WORDS.search(message) or (
            parsed.per_month and (parsed.months or _CADENCE_HINT.search(message))
        )
        if asks_cadence:
            return Intent.CADENCE
        if _PLAN_ANY.search(message) or (not has_context and _PLAN_OPEN.search(message)):
            return Intent.PLAN
        return classify(message)
    if _PLAN_STRONG.search(message):
        return Intent.PLAN  # no amount yet: the plan task will ask for it
    return classify(message)
