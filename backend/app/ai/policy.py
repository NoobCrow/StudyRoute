"""Policy check on user messages and document text (blueprint 14.2 step 2).

Text is data, never instructions. This module flags attempts to override the rules, trigger
payments, change limits or config, reveal secrets or make the assistant invent numbers.
Flagged messages are answered with a fixed refusal and recorded in the audit log.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_I = re.I
_QUALIFIER = r"(?:(?:all|any|the|your|these|those|previous|prior|above|earlier|system|safety)\s+)*"
_VERB = r"(?:approve|submit|release|authori[sz]e|execute|send|wire|transfer|pay|cancel|refund)"
_LEAD = r"(?:^|[.!?;:,\n]\s*|\band\s+|\bthen\s+|\bplease\s+|\bjust\s+|\bnow\s+)"

PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "INSTRUCTION_OVERRIDE": [
        re.compile(
            rf"\b(?:ignore|disregard|forget|override|bypass)\s+{_QUALIFIER}(?:instructions?|rules?|prompts?|guidelines?|polic(?:y|ies)|limits?|restrictions?)",
            _I,
        ),
        re.compile(r"\bnew\s+(?:rules?|instructions?)\b", _I),
        re.compile(r"(?:^|[\n.!?]\s*)(?:system|assistant|developer)\s*:", _I),
        re.compile(r"\b(?:jailbreak|developer\s+mode|dan\s+mode)\b", _I),
        re.compile(
            r"\byou\s+are\s+now\b|\bpretend\s+(?:to\s+be|you)\b|\bact\s+as\s+(?:an?\s+)?(?:admin|root)\b",
            _I,
        ),
    ],
    "ACTION_REQUEST": [
        re.compile(
            rf"{_LEAD}{_VERB}\b.{{0,60}}\b(?:payment|transfer|transaction|money|funds|it|now|pay_\w+)\b",
            _I,
        ),
        re.compile(rf"{_LEAD}(?:approve|submit|release)\b", _I),
        re.compile(rf"\b(?:can|could|would|will)\s+you\s+(?:please\s+)?{_VERB}\b", _I),
        re.compile(rf"\byou\s+(?:to|should|must)\s+{_VERB}\b", _I),
        re.compile(r"\bpay\s+now\b|\bgo\s+ahead\s+and\s+(?:pay|send|approve)\b", _I),
    ],
    "LIMIT_CHANGE": [
        re.compile(
            r"\b(?:raise|increase|change|set|update|remove|lift|bump|double|disable)\b.{0,40}\b(?:limit|cap|quota)\b",
            _I,
        ),
    ],
    "CONFIG_CHANGE": [
        re.compile(
            r"\b(?:edit|change|update|modify|set|disable|turn\s+off)\b.{0,25}\b(?:config(?:uration)?|rules?|settings?|kyc|mfa|audit(?:\s+log)?)\b",
            _I,
        ),
    ],
    "PRIVILEGE_CLAIM": [
        re.compile(
            r"\bi\s*(?:am|'m)\s+(?:the\s+|an?\s+)?(?:admin|administrator|owner|root|developer|reviewer|bank|auditor)\b",
            _I,
        ),
        re.compile(r"\bas\s+(?:the\s+)?(?:admin|administrator)\b", _I),
    ],
    "SECRET_REQUEST": [
        re.compile(
            r"\b(?:print|show|reveal|display|repeat|leak|dump|tell\s+me|give\s+me)\b.{0,40}\b(?:system\s+prompt|your\s+(?:prompt|instructions|rules)|api\s*key|secret|password|token|credentials)\b",
            _I,
        ),
        re.compile(
            r"\b(?:other|another|someone\s+else)(?:'s)?\s+(?:user|customer|parent|student)(?:'s)?\b.{0,30}\b(?:account|data|number|iban|details|passport)\b",
            _I,
        ),
        re.compile(r"\baccount\s+number\s+of\b", _I),
    ],
    "FABRICATION_REQUEST": [
        re.compile(
            r"\b(?:make\s+up|invent|fabricate|guess|estimate\s+wildly)\b.{0,30}\b(?:number|figure|rate|cost|price|amount|percentage)\b",
            _I,
        ),
        re.compile(r"\bjust\s+guess\b", _I),
    ],
    "LEGAL_QUESTION": [
        re.compile(
            r"\b(?:is\s+it|is\s+this|is\s+that|are\s+we|would\s+it\s+be|confirm(?:\s+it\s+is|\s+that)?)\b.{0,40}\b(?:legal|lawful|allowed|permitted|within\s+the\s+limit|compliant)\b",
            _I,
        ),
        re.compile(r"\blegal(?:ly)?\b.{0,20}\b(?:limit|to\s+send|to\s+remit)\b", _I),
    ],
}

NON_BLOCKING = {"LEGAL_QUESTION"}


@dataclass(frozen=True)
class PolicyResult:
    flags: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return any(flag not in NON_BLOCKING for flag in self.flags)

    @property
    def legal_question(self) -> bool:
        return "LEGAL_QUESTION" in self.flags


def check_text(text: str) -> PolicyResult:
    flags = [name for name, patterns in PATTERNS.items() if any(p.search(text) for p in patterns)]
    return PolicyResult(tuple(flags))
