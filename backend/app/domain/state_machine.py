"""Payment state machine (blueprint section 10) as a transition table.

Pure: no database, no clock. The payment service supplies a GuardContext and persists the
result together with exactly one audit event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core import errors
from app.domain.constants import ActorKind, PaymentState

S = PaymentState
K = ActorKind

SANDBOX_CAP_MESSAGE = "Sandbox cap exceeded (indicative). Confirm with your AD bank."


class Event(StrEnum):
    QUOTE_ATTACHED = "quote_attached"
    REQUEST_APPROVAL = "request_approval"
    QUOTE_EXPIRED = "quote_expired"
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
    SUBMIT = "submit"
    PROVIDER_SETTLED = "provider_settled"
    PROVIDER_FAILED = "provider_failed"


class Guard(StrEnum):
    QUOTE_VALID = "quote_valid"
    KYC_VERIFIED = "kyc_verified"
    RECIPIENT_ALLOWLISTED = "recipient_allowlisted"
    SANCTIONS_CLEAR = "sanctions_clear"
    WITHIN_LIMITS = "within_limits"
    FRESH_MFA = "fresh_mfa"
    SUMMARY_MATCHES = "summary_matches"


@dataclass(frozen=True)
class Transition:
    event: Event
    sources: frozenset[PaymentState]
    target: PaymentState
    actors: frozenset[ActorKind]
    guards: tuple[Guard, ...] = ()


_ACTION_GUARDS = (
    Guard.QUOTE_VALID,
    Guard.KYC_VERIFIED,
    Guard.RECIPIENT_ALLOWLISTED,
    Guard.SANCTIONS_CLEAR,
    Guard.WITHIN_LIMITS,
)

TRANSITIONS: tuple[Transition, ...] = (
    Transition(
        Event.QUOTE_ATTACHED,
        frozenset({S.DRAFT}),
        S.QUOTED,
        frozenset({K.SYSTEM, K.PARENT, K.AI}),
        (Guard.QUOTE_VALID,),
    ),
    Transition(
        Event.REQUEST_APPROVAL,
        frozenset({S.QUOTED}),
        S.PENDING_APPROVAL,
        frozenset({K.PARENT, K.AI}),
        _ACTION_GUARDS,
    ),
    Transition(
        Event.QUOTE_EXPIRED,
        frozenset({S.QUOTED, S.PENDING_APPROVAL}),
        S.DRAFT,
        frozenset({K.SYSTEM}),
    ),
    Transition(
        Event.APPROVE,
        frozenset({S.PENDING_APPROVAL}),
        S.APPROVED,
        frozenset({K.PARENT}),
        (Guard.FRESH_MFA, *_ACTION_GUARDS, Guard.SUMMARY_MATCHES),
    ),
    Transition(
        Event.REJECT,
        frozenset({S.PENDING_APPROVAL}),
        S.REJECTED,
        frozenset({K.PARENT, K.ADMIN}),
    ),
    # Blueprint 10 allows cancelling an APPROVED payment. We also let the parent discard a
    # draft or an unapproved payment (documented as an extension in the blueprint addendum).
    Transition(
        Event.CANCEL,
        frozenset({S.DRAFT, S.QUOTED, S.PENDING_APPROVAL, S.APPROVED}),
        S.CANCELLED,
        frozenset({K.PARENT}),
    ),
    Transition(Event.SUBMIT, frozenset({S.APPROVED}), S.SUBMITTED, frozenset({K.SYSTEM})),
    Transition(
        Event.PROVIDER_SETTLED, frozenset({S.SUBMITTED}), S.SETTLED, frozenset({K.PROVIDER})
    ),
    Transition(Event.PROVIDER_FAILED, frozenset({S.SUBMITTED}), S.FAILED, frozenset({K.PROVIDER})),
)

_BY_EVENT: dict[Event, Transition] = {t.event: t for t in TRANSITIONS}


def next_state(state: PaymentState, event: Event, actor: ActorKind) -> PaymentState:
    """Return the new state, or raise Forbidden / AiCannotApprove / InvalidState."""
    transition = _BY_EVENT[event]
    if actor not in transition.actors:
        if event is Event.APPROVE and actor is K.AI:
            raise errors.AiCannotApprove("Only a human parent can approve a payment.")
        raise errors.Forbidden(f"{actor.value} may not trigger '{event.value}'.")
    if state not in transition.sources:
        raise errors.InvalidState(f"Cannot apply '{event.value}' to a payment in state {state}.")
    return transition.target


@dataclass(frozen=True)
class GuardContext:
    now: datetime
    quote_expires_at: datetime | None
    kyc_verified: bool
    recipient_allowlisted: bool
    sanctions_clear: bool
    limit_error: str | None
    mfa_valid: bool
    summary_matches: bool


def _check(guard: Guard, ctx: GuardContext) -> None:
    if guard is Guard.QUOTE_VALID:
        if ctx.quote_expires_at is None:
            raise errors.ValidationFailed("The payment has no quote attached.")
        if ctx.now >= ctx.quote_expires_at:
            raise errors.QuoteExpired("Request a new quote before continuing.")
    elif guard is Guard.KYC_VERIFIED and not ctx.kyc_verified:
        raise errors.KycNotVerified(
            "KYC is not verified (simulated). Approval is blocked until it is.",
            persist=True,
        )
    elif guard is Guard.RECIPIENT_ALLOWLISTED and not ctx.recipient_allowlisted:
        raise errors.RecipientNotAllowlisted(
            "Allowlist the recipient first. This needs an MFA step.", persist=True
        )
    elif guard is Guard.SANCTIONS_CLEAR and not ctx.sanctions_clear:
        raise errors.SanctionsHit(
            "The recipient matched the mock sanctions screening.", persist=True
        )
    elif guard is Guard.WITHIN_LIMITS and ctx.limit_error:
        raise errors.LimitExceeded(
            SANDBOX_CAP_MESSAGE, persist=True, extra={"limit": ctx.limit_error}
        )
    elif guard is Guard.FRESH_MFA and not ctx.mfa_valid:
        raise errors.MfaRequired(
            "Verify MFA again. The proof is missing, already used, or older than 5 minutes.",
            persist=True,
        )
    elif guard is Guard.SUMMARY_MATCHES and not ctx.summary_matches:
        raise errors.SummaryMismatch(
            "The payment details changed after the summary was shown. Review it again.",
            persist=True,
        )


def check_guards(event: Event, ctx: GuardContext) -> None:
    """Run the guards for `event` in order. The first failure raises its blueprint error."""
    for guard in _BY_EVENT[event].guards:
        _check(guard, ctx)
