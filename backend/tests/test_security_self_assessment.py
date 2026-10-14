"""The permission matrix in docs/SECURITY_SELF_ASSESSMENT.md must equal the code."""

from __future__ import annotations

import re
from pathlib import Path

from app.domain.constants import ActorKind
from app.domain.rbac import ROLE_PERMISSIONS, Perm

DOC = Path(__file__).resolve().parents[2] / "docs" / "SECURITY_SELF_ASSESSMENT.md"
KINDS = (ActorKind.PARENT, ActorKind.STUDENT, ActorKind.ADMIN, ActorKind.AI)
ROW = re.compile(r"^\| `([a-z_]+:[a-z_]+)` \| (yes|-) \| (yes|-) \| (yes|-) \| (yes|-) \|$", re.M)


def documented() -> dict[str, tuple[str, ...]]:
    return {m.group(1): tuple(m.groups()[1:]) for m in ROW.finditer(DOC.read_text("utf-8"))}


def test_every_permission_is_documented_exactly_as_the_code_grants_it() -> None:
    expected = {
        perm.value: tuple("yes" if perm in ROLE_PERMISSIONS[kind] else "-" for kind in KINDS)
        for perm in Perm
    }
    assert documented() == expected


def test_the_documented_ai_tier_never_includes_a_decision() -> None:
    ai_column = {perm: row[3] for perm, row in documented().items()}
    for decision in (
        "payments:approve",
        "payments:cancel",
        "payments:reject",
        "recipients:allowlist",
        "config:write",
        "audit:verify",
        "sandbox:control",
        "bank:transfer",
    ):
        assert ai_column[decision] == "-", decision


def test_the_known_risk_list_is_present_and_numbered() -> None:
    text = DOC.read_text("utf-8")
    ids = re.findall(r"^\| (R\d+) \|", text, re.M)
    assert ids == [f"R{n}" for n in range(1, len(ids) + 1)]
    assert len(ids) >= 15
