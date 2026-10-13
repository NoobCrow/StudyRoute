"""Rule-based intent detection for template mode (no model needed)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum


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


_RULES: list[tuple[Intent, re.Pattern[str]]] = [
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
            r"\bstatus\b|where\s+is|tracker|\btrack\b|\buetr\b|settled|delivered|\barrive", re.I
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
