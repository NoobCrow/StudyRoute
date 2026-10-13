"""Payment state machine (blueprint 10). T15 and the guard behaviour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core import errors
from app.domain.constants import TERMINAL_STATES, ActorKind, PaymentState
from app.domain.state_machine import (
    TRANSITIONS,
    Event,
    GuardContext,
    check_guards,
    next_state,
)

S = PaymentState
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)


def ok_context(**overrides: object) -> GuardContext:
    base: dict[str, object] = {
        "now": NOW,
        "quote_expires_at": NOW + timedelta(seconds=120),
        "kyc_verified": True,
        "recipient_allowlisted": True,
        "sanctions_clear": True,
        "limit_error": None,
        "mfa_valid": True,
        "summary_matches": True,
    }
    base.update(overrides)
    return GuardContext(**base)  # type: ignore[arg-type]


def test_happy_path_follows_the_blueprint_diagram() -> None:
    state = S.DRAFT
    for event, actor in [
        (Event.QUOTE_ATTACHED, ActorKind.SYSTEM),
        (Event.REQUEST_APPROVAL, ActorKind.PARENT),
        (Event.APPROVE, ActorKind.PARENT),
        (Event.SUBMIT, ActorKind.SYSTEM),
        (Event.PROVIDER_SETTLED, ActorKind.PROVIDER),
    ]:
        state = next_state(state, event, actor)
    assert state is S.SETTLED


def test_table_matches_blueprint_section_10() -> None:
    expected = {
        (S.DRAFT, Event.QUOTE_ATTACHED): S.QUOTED,
        (S.QUOTED, Event.REQUEST_APPROVAL): S.PENDING_APPROVAL,
        (S.QUOTED, Event.QUOTE_EXPIRED): S.DRAFT,
        (S.PENDING_APPROVAL, Event.QUOTE_EXPIRED): S.DRAFT,
        (S.PENDING_APPROVAL, Event.APPROVE): S.APPROVED,
        (S.PENDING_APPROVAL, Event.REJECT): S.REJECTED,
        (S.APPROVED, Event.CANCEL): S.CANCELLED,
        (S.APPROVED, Event.SUBMIT): S.SUBMITTED,
        (S.SUBMITTED, Event.PROVIDER_SETTLED): S.SETTLED,
        (S.SUBMITTED, Event.PROVIDER_FAILED): S.FAILED,
    }
    blueprint = {(state, t.event): t.target for t in TRANSITIONS for state in t.sources}
    for key, target in expected.items():
        assert blueprint[key] is target
    extension = {k for k in blueprint if k not in expected}
    assert {event for _, event in extension} == {Event.CANCEL}
    assert {state for state, _ in extension} == {S.DRAFT, S.QUOTED, S.PENDING_APPROVAL}


def test_T15_settled_to_submitted_is_an_illegal_transition() -> None:
    with pytest.raises(errors.InvalidState):
        next_state(S.SETTLED, Event.SUBMIT, ActorKind.SYSTEM)


def test_every_event_on_a_terminal_state_is_invalid() -> None:
    for state in TERMINAL_STATES:
        for event in Event:
            for actor in ActorKind:
                with pytest.raises((errors.InvalidState, errors.Forbidden, errors.AiCannotApprove)):
                    next_state(state, event, actor)


def test_every_combination_outside_the_table_is_invalid_state() -> None:
    allowed = {(state, t.event) for t in TRANSITIONS for state in t.sources}
    actors = {t.event: sorted(t.actors)[0] for t in TRANSITIONS}
    for state in PaymentState:
        for event in Event:
            if (state, event) in allowed:
                continue
            with pytest.raises(errors.InvalidState):
                next_state(state, event, actors[event])


def test_ai_can_never_approve_and_gets_the_dedicated_error() -> None:
    with pytest.raises(errors.AiCannotApprove):
        next_state(S.PENDING_APPROVAL, Event.APPROVE, ActorKind.AI)


@pytest.mark.parametrize("actor", [ActorKind.STUDENT, ActorKind.ADMIN, ActorKind.SYSTEM])
def test_only_a_parent_can_approve(actor: ActorKind) -> None:
    with pytest.raises(errors.Forbidden):
        next_state(S.PENDING_APPROVAL, Event.APPROVE, actor)


def test_reject_is_for_parent_or_admin_only() -> None:
    assert next_state(S.PENDING_APPROVAL, Event.REJECT, ActorKind.ADMIN) is S.REJECTED
    assert next_state(S.PENDING_APPROVAL, Event.REJECT, ActorKind.PARENT) is S.REJECTED
    for actor in (ActorKind.AI, ActorKind.STUDENT):
        with pytest.raises(errors.Forbidden):
            next_state(S.PENDING_APPROVAL, Event.REJECT, actor)


def test_cancel_is_parent_only_and_ai_cannot_cancel() -> None:
    assert next_state(S.APPROVED, Event.CANCEL, ActorKind.PARENT) is S.CANCELLED
    for actor in (ActorKind.AI, ActorKind.ADMIN, ActorKind.STUDENT):
        with pytest.raises(errors.Forbidden):
            next_state(S.APPROVED, Event.CANCEL, actor)


def test_only_the_system_submits_and_only_a_provider_settles() -> None:
    with pytest.raises(errors.Forbidden):
        next_state(S.APPROVED, Event.SUBMIT, ActorKind.PARENT)
    with pytest.raises(errors.Forbidden):
        next_state(S.SUBMITTED, Event.PROVIDER_SETTLED, ActorKind.PARENT)
    with pytest.raises(errors.Forbidden):
        next_state(S.SUBMITTED, Event.PROVIDER_FAILED, ActorKind.AI)


def test_ai_and_parent_may_request_approval_but_student_may_not() -> None:
    for actor in (ActorKind.AI, ActorKind.PARENT):
        assert next_state(S.QUOTED, Event.REQUEST_APPROVAL, actor) is S.PENDING_APPROVAL
    with pytest.raises(errors.Forbidden):
        next_state(S.QUOTED, Event.REQUEST_APPROVAL, ActorKind.STUDENT)


def test_request_approval_guards_pass_when_everything_is_in_order() -> None:
    check_guards(Event.REQUEST_APPROVAL, ok_context())


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"kyc_verified": False}, errors.KycNotVerified),
        ({"recipient_allowlisted": False}, errors.RecipientNotAllowlisted),
        ({"sanctions_clear": False}, errors.SanctionsHit),
        ({"limit_error": "DAILY_CAP"}, errors.LimitExceeded),
        ({"quote_expires_at": NOW - timedelta(seconds=1)}, errors.QuoteExpired),
        ({"quote_expires_at": NOW}, errors.QuoteExpired),
    ],
)
def test_guards_raise_the_blueprint_error_codes(
    overrides: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        check_guards(Event.REQUEST_APPROVAL, ok_context(**overrides))
    with pytest.raises(error):
        check_guards(Event.APPROVE, ok_context(**overrides))


def test_approve_needs_fresh_mfa_and_a_matching_summary() -> None:
    with pytest.raises(errors.MfaRequired):
        check_guards(Event.APPROVE, ok_context(mfa_valid=False))
    with pytest.raises(errors.SummaryMismatch):
        check_guards(Event.APPROVE, ok_context(summary_matches=False))
    check_guards(Event.APPROVE, ok_context())


def test_mfa_is_checked_before_quote_expiry_so_a_stale_quote_needs_no_leak() -> None:
    both_bad = ok_context(mfa_valid=False, quote_expires_at=NOW - timedelta(seconds=5))
    with pytest.raises(errors.MfaRequired):
        check_guards(Event.APPROVE, both_bad)


def test_events_without_guards_pass_through() -> None:
    for event in (Event.REJECT, Event.CANCEL, Event.SUBMIT, Event.PROVIDER_SETTLED):
        check_guards(event, ok_context(kyc_verified=False, mfa_valid=False))
