"""Tool allow-list (blueprint 14.3). The assistant can read, and it can PROPOSE two steps.

Proposals are never executed by the assistant: the user confirms them in the app, using their
own token. approve, submit, cancel, change_limit, allowlist_recipient and edit_config do not
exist for the AI at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.core import errors
from app.domain.rbac import Actor, Perm, authorize


@dataclass(frozen=True)
class ToolSpec:
    name: str
    effect: str
    side_effects: str
    human_needed: str
    permission: Perm
    allowed_args: frozenset[str]
    executes: bool  # True: the orchestrator runs it (read only). False: proposal only.


TOOLS: dict[str, ToolSpec] = {
    spec.name: spec
    for spec in (
        ToolSpec("get_quotes", "Reads ranked quotes", "none", "no", Perm.QUOTE_READ, frozenset({"quote_id"}), True),
        ToolSpec("explain_cost", "Reads the cost breakdown", "none", "no", Perm.QUOTE_READ, frozenset({"quote_id", "provider_id"}), True),
        ToolSpec("get_deadline_plan", "Reads the planner output", "none", "no", Perm.PLANNER_READ, frozenset({"due_date", "country"}), True),
        ToolSpec("get_checklist", "Reads the document checklist", "none", "no", Perm.CHECKLIST_READ, frozenset({"country", "purpose"}), True),
        ToolSpec("create_draft", "Proposes a DRAFT payment", "writes a draft", "the user clicks Confirm draft", Perm.PAYMENT_CREATE_DRAFT, frozenset({"quote_id", "provider_id", "recipient_id", "reference"}), False),
        ToolSpec("request_approval", "Proposes moving to PENDING_APPROVAL", "state change", "the user then approves", Perm.PAYMENT_REQUEST_APPROVAL, frozenset({"payment_id"}), False),
    )
}  # fmt: skip

NOT_AVAILABLE_TO_AI = frozenset(
    {"approve", "submit", "cancel", "change_limit", "allowlist_recipient", "edit_config"}
)
_ARG_VALUE = re.compile(r"^[A-Za-z0-9_./ -]{1,80}$")


@dataclass(frozen=True)
class ToolDecision:
    allowed: bool
    reason: str | None = None
    spec: ToolSpec | None = None


def validate_proposal(actor: Actor, name: str, args: dict[str, Any]) -> ToolDecision:
    """Allow-list first, then the SAME permission check a human call would face."""
    if name in NOT_AVAILABLE_TO_AI:
        return ToolDecision(False, "NOT_AVAILABLE_TO_AI")
    spec = TOOLS.get(name)
    if spec is None:
        return ToolDecision(False, "UNKNOWN_TOOL")
    if spec.executes:
        return ToolDecision(False, "NOT_A_PROPOSAL")
    try:
        authorize(actor, spec.permission)
    except errors.ApiError:
        return ToolDecision(False, "PERMISSION_DENIED")
    if not set(args) <= spec.allowed_args:
        return ToolDecision(False, "BAD_ARGS")
    if not all(isinstance(v, str) and _ARG_VALUE.match(v) for v in args.values()):
        return ToolDecision(False, "BAD_ARGS")
    return ToolDecision(True, None, spec)
