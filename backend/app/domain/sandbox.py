"""Sandbox description and the reviewer's control over the simulated provider.

Nothing here moves money or changes a payment directly. Triggering a provider event only
brings the simulator's next signed webhook forward (or turns it into a failure), so the
real webhook verification and the state machine still do all the work. Sandbox mode only.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock
from app.core.config import Settings
from app.core.demo import demo_hints
from app.domain.constants import PaymentState
from app.domain.payments import PaymentService
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import Rules
from app.models import ProviderLedger
from app.providers.base import ProviderStatus, Scenario

BANNER = "Sandbox - synthetic data - no real money moves"
DISCLAIMER = "Indicative guidance only. Confirm with your AD bank."

SIMULATED: list[dict[str, str]] = [
    {
        "component": "Providers A, B and C",
        "what": "Invented fees and margins. No bank is contacted.",
    },
    {"component": "Exchange rates", "what": "Synthetic mid-market rates. Not a live FX feed."},
    {"component": "KYC review", "what": "A timer moves a mock status. No real identity data."},
    {
        "component": "SWIFT messages",
        "what": "The MT103 and pacs.008 are previews. Nothing is sent.",
    },
    {"component": "Settlement", "what": "A simulator sends HMAC-signed status webhooks."},
    {"component": "Host-country rails", "what": "Named in the tracker only. Not simulated."},
    {"component": "Documents", "what": "Mock text files. Never upload a real passport or ID."},
]


def describe_sandbox(settings: Settings, rules: Rules, ai_mode: str) -> dict[str, Any]:
    """The public description of what is simulated and how to exercise it."""
    hints = demo_hints(settings)
    return {
        "sandbox": True,
        "banner": BANNER,
        "disclaimer": DISCLAIMER,
        "simulated": SIMULATED,
        "scenarios": [
            {
                "token": rules.fail_token,
                "where": "Recipient name",
                "effect": "The simulated provider rejects the payment (it ends FAILED).",
            },
            {
                "token": rules.slow_token,
                "where": "Recipient name",
                "effect": f"Settlement takes {settings.slow_settle_delay_seconds} seconds.",
            },
            {
                "token": rules.sanctions_token,
                "where": "Recipient name",
                "effect": "Blocked by the mock sanctions check and written to the audit log.",
            },
        ],
        "providers": [
            {"provider_id": t.provider_id, "name": t.name} for t in rules.provider_terms()
        ],
        "timings": {
            "quote_ttl_seconds": rules.quote_ttl_seconds,
            "mfa_proof_ttl_seconds": rules.mfa_proof_ttl_seconds,
            "kyc_review_seconds": rules.kyc_review_seconds,
            "submit_delay_seconds": settings.submit_delay_seconds,
            "settle_delay_seconds": settings.settle_delay_seconds,
            "slow_settle_delay_seconds": settings.slow_settle_delay_seconds,
        },
        "limits": {
            "per_transaction_usd_equivalent": rules.per_transaction_limit_usd,
            "daily_usd_equivalent": rules.daily_limit_usd,
            "indicative": "Sandbox caps of our own choosing. Not legal limits.",
        },
        "ai_mode": ai_mode,
        "demo": hints,
    }


class SandboxService:
    def __init__(self, clock: Clock, audit: AuditService, payments: PaymentService) -> None:
        self._clock = clock
        self._audit = audit
        self._payments = payments

    def schedule_provider_event(
        self, session: Session, actor: Actor, payment_id: str, outcome: str
    ) -> dict[str, Any]:
        """Make the simulator send the signed settle or fail webhook on its next tick."""
        authorize(actor, Perm.SANDBOX_CONTROL)
        payment = self._payments.load(session, actor, payment_id)
        if payment.state != PaymentState.SUBMITTED.value or payment.uetr is None:
            raise errors.InvalidState(
                "Only a SUBMITTED payment is in flight at the simulated provider."
            )
        ledger = session.get(ProviderLedger, payment.uetr)
        if ledger is None or ledger.status != ProviderStatus.ACCEPTED.value:
            raise errors.InvalidState("The simulated provider already reported on this payment.")
        ledger.scenario = Scenario.FAIL.value if outcome == "fail" else Scenario.NORMAL.value
        ledger.due_at = self._clock.now()
        event = "payment.failed" if outcome == "fail" else "payment.settled"
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="sandbox.provider_event_scheduled",
            payment_id=payment.id,
            reason_code=event.upper().replace(".", "_"),
            detail=f"{event} brought forward (simulated)",
        )
        return {
            "payment_id": payment.id,
            "event": event,
            "scheduled": True,
            "simulated": True,
            "note": "The signed webhook is sent on the simulator's next tick (about a second).",
        }
