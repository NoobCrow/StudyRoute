"""Output guards for model replies (blueprint 14.2 steps 6 and 7).

A reply is accepted only if it is well-formed JSON, uses only numbers from the FACTS, does not
claim to have acted, does not call anything legal or "within the limit", and proposes only
allow-listed tools. Anything else is discarded and the deterministic template is used.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.ai.claim_checks import claim_failure
from app.ai.facts import FactSet
from app.ai.number_guard import check_numbers
from app.ai.templates import INDICATIVE
from app.ai.tools import validate_proposal
from app.domain.rbac import Actor

MAX_REPLY_CHARS = 2000
MAX_PROPOSALS = 2

_ACTION_CLAIM = re.compile(
    r"\bi\s*(?:have\s+|'ve\s+|just\s+|already\s+)*(?:approved|submitted|sent|paid|cancell?ed|released|"
    r"transferred|changed|raised|increased|lifted|allowlisted|verified|updated)\b"
    r"|\b(?:payment|transfer)\s+(?:has\s+been|was|is\s+now)\s+(?:approved|submitted|sent|released)\b",
    re.I,
)
_LEGAL_CLAIM = re.compile(
    r"\b(?:is|are|it's|that's)\s+(?:perfectly\s+|fully\s+|completely\s+)?(?:legal|lawful|compliant)\b"
    r"|\bwithin\s+(?:the\s+|your\s+)(?:legal\s+)?limits?\b",
    re.I,
)


_HEDGE = re.compile(r"\b(?:whether|if)\b[^.!?]{0,60}", re.I)


class GuardFailure(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class ValidatedReply:
    reply: str
    facts_used: list[str]
    proposals: list[dict[str, Any]] = field(default_factory=list)


def parse_llm_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    for attempt in (candidate, candidate[candidate.find("{") : candidate.rfind("}") + 1]):
        try:
            parsed = json.loads(attempt)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise GuardFailure("BAD_JSON", "The reply was not a JSON object.")


def _proposals(raw: Any, actor: Actor) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
            continue
        name = item["tool"]
        try:
            args = json.loads(item.get("args_json") or "{}")
        except ValueError:
            continue
        if not isinstance(args, dict):
            continue
        decision = validate_proposal(actor, name, args)
        if decision.reason in {
            "NOT_AVAILABLE_TO_AI",
            "UNKNOWN_TOOL",
            "PERMISSION_DENIED",
            "NOT_A_PROPOSAL",
        }:
            raise GuardFailure("TOOL_NOT_ALLOWED", f"{name}: {decision.reason}")
        if decision.allowed:
            kept.append({"tool": name, "args": args, "requires_human": True, "missing": []})
    return kept[:MAX_PROPOSALS]


def validate_llm_output(
    parsed: dict[str, Any], *, facts: FactSet, actor: Actor, legal_question: bool
) -> ValidatedReply:
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip() or len(reply) > MAX_REPLY_CHARS:
        raise GuardFailure("BAD_SHAPE", "reply missing, empty or too long")
    if failure := claim_failure(reply, facts):
        raise GuardFailure(failure, "unsafe success promise or ungrounded account/limit wording")
    if _ACTION_CLAIM.search(reply):
        raise GuardFailure("ACTION_CLAIM", "the reply claims an action was taken")
    if _LEGAL_CLAIM.search(_HEDGE.sub(" ", reply)):  # "I cannot say whether it is legal" is fine
        raise GuardFailure("LEGAL_CLAIM", "the reply calls something legal or within a limit")
    numbers = check_numbers(reply, facts.numbers())
    if not numbers.ok:
        raise GuardFailure("NUMBER_GUARD", "numbers not in FACTS: " + ", ".join(numbers.offending))
    used = [f for f in parsed.get("facts_used", []) if isinstance(f, str) and f in facts.ids()]
    proposals = _proposals(parsed.get("proposed_actions"), actor)
    if legal_question and INDICATIVE not in reply:
        reply = f"{reply.rstrip()} {INDICATIVE}"
    return ValidatedReply(reply.strip(), list(dict.fromkeys(used)), proposals)
