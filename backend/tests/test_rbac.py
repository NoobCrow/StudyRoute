"""RBAC matrix from blueprint 12.2, checked permission by permission."""

from __future__ import annotations

import pytest

from app.core import errors
from app.domain.constants import ActorKind
from app.domain.rbac import ROLE_PERMISSIONS, Actor, Perm, authorize, make_actor

P, S, A, AI = ActorKind.PARENT, ActorKind.STUDENT, ActorKind.ADMIN, ActorKind.AI

MATRIX: dict[Perm, dict[ActorKind, bool]] = {
    Perm.QUOTE_READ: {P: True, S: True, A: True, AI: True},
    Perm.PAYMENT_READ: {P: True, S: True, A: True, AI: True},
    Perm.QUOTE_CREATE: {P: True, S: True, A: False, AI: True},
    Perm.PAYMENT_CREATE_DRAFT: {P: True, S: False, A: False, AI: True},
    Perm.PAYMENT_REQUEST_APPROVAL: {P: True, S: False, A: False, AI: True},
    Perm.PAYMENT_APPROVE: {P: True, S: False, A: False, AI: False},
    Perm.PAYMENT_CANCEL: {P: True, S: False, A: False, AI: False},
    Perm.PAYMENT_REJECT: {P: True, S: False, A: True, AI: False},
    Perm.RECIPIENT_ALLOWLIST: {P: True, S: False, A: False, AI: False},
    Perm.CONFIG_WRITE: {P: False, S: False, A: True, AI: False},
    Perm.AUDIT_READ: {P: True, S: False, A: True, AI: False},
    Perm.AUDIT_VERIFY: {P: False, S: False, A: True, AI: False},
    Perm.SANDBOX_CONTROL: {P: False, S: False, A: True, AI: False},
}


@pytest.mark.parametrize(("perm", "row"), list(MATRIX.items()))
def test_role_permissions_match_the_blueprint_matrix(
    perm: Perm, row: dict[ActorKind, bool]
) -> None:
    for kind, allowed in row.items():
        assert (perm in ROLE_PERMISSIONS[kind]) is allowed, (perm, kind)


def test_authorize_allows_and_denies() -> None:
    parent = make_actor(P, "usr_p", owner_id="usr_p")
    student = make_actor(S, "usr_s", owner_id="usr_p")
    authorize(parent, Perm.PAYMENT_APPROVE)
    with pytest.raises(errors.Forbidden):
        authorize(student, Perm.PAYMENT_APPROVE)


def test_the_ai_actor_gets_a_dedicated_error_for_approve() -> None:
    ai = make_actor(AI, "usr_ai", owner_id="usr_p", on_behalf_of="usr_p")
    with pytest.raises(errors.AiCannotApprove):
        authorize(ai, Perm.PAYMENT_APPROVE)


@pytest.mark.parametrize(
    "perm",
    [
        Perm.PAYMENT_APPROVE,
        Perm.PAYMENT_CANCEL,
        Perm.PAYMENT_REJECT,
        Perm.RECIPIENT_ALLOWLIST,
        Perm.CONFIG_WRITE,
        Perm.AUDIT_READ,
        Perm.AUDIT_VERIFY,
        Perm.KYC_REVIEW,
        Perm.MFA_ISSUE,
        Perm.SANDBOX_CONTROL,
    ],
)
def test_the_ai_has_no_mutating_or_privileged_permission(perm: Perm) -> None:
    assert perm not in ROLE_PERMISSIONS[AI]
    ai = make_actor(AI, "usr_ai", owner_id="usr_p", on_behalf_of="usr_p")
    assert perm.value not in ai.scopes


def test_scopes_are_enforced_even_when_the_role_would_allow() -> None:
    narrowed = Actor(
        kind=P, user_id="usr_p", owner_id="usr_p", scopes=frozenset({Perm.QUOTE_READ.value})
    )
    authorize(narrowed, Perm.QUOTE_READ)
    with pytest.raises(errors.Forbidden):
        authorize(narrowed, Perm.PAYMENT_APPROVE)


def test_system_and_provider_actors_hold_no_user_permissions() -> None:
    for kind in (ActorKind.SYSTEM, ActorKind.PROVIDER):
        assert not ROLE_PERMISSIONS[kind]


def test_owner_scoping_rules() -> None:
    parent = make_actor(P, "usr_p", owner_id="usr_p")
    student = make_actor(S, "usr_s", owner_id="usr_p")
    admin = make_actor(A, "usr_a", owner_id=None)
    assert parent.can_see_owner("usr_p")
    assert student.can_see_owner("usr_p")
    assert not parent.can_see_owner("usr_other")
    assert admin.can_see_owner("usr_other")
