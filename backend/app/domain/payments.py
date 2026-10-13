"""Payments: the state machine in action, with one audit event per transition.

Every method runs inside the caller's database transaction. Authorisation, guards, the state
change, the transition history and the audit event all commit together or not at all.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import hash_object
from app.core.ids import new_id
from app.domain import auth
from app.domain.compliance import is_sanctions_hit, scenario_for
from app.domain.constants import Decision, PaymentState
from app.domain.kyc import KycService
from app.domain.limits import evaluate_limits, usd_equivalent_minor
from app.domain.quotes import QuoteService
from app.domain.rbac import SYSTEM_ACTOR, Actor, Perm, authorize, provider_actor
from app.domain.recipients import RecipientService
from app.domain.rules import Rules
from app.domain.state_machine import Event, GuardContext, check_guards, next_state
from app.engine.money import Money
from app.engine.mt103 import build_instruction_preview
from app.engine.planner import plan_deadline
from app.engine.quote import ChargeCode
from app.engine.validators import is_valid_swift_reference, mask_account, new_uetr
from app.models import Payment, PaymentTransition, Quote, Recipient, User
from app.providers.base import SubmitInstruction
from app.providers.registry import ProviderRegistry

DHAKA = ZoneInfo("Asia/Dhaka")
COUNTS_TOWARD_DAILY_CAP = (
    PaymentState.PENDING_APPROVAL.value,
    PaymentState.APPROVED.value,
    PaymentState.SUBMITTED.value,
    PaymentState.SETTLED.value,
)
SUMMARY_DISCLAIMER = "Sandbox. No real money moves. Indicative guidance only."
COMPLIANCE_CODES = {"SANCTIONS_HIT", "LIMIT_EXCEEDED"}


def build_summary(
    payment: Payment, quote: Quote, result: dict[str, Any], recipient_label: str
) -> dict[str, Any]:
    """The facts a human must read before approving. Its hash binds the approval to them."""
    receives = Money(result["beneficiary_receives_minor"], quote.target_currency)
    latest = payment.latest_send_date
    return {
        "payment_id": payment.id,
        "quote_id": quote.id,
        "provider_id": result["provider_id"],
        "provider_name": result["provider_name"],
        "recipient": recipient_label,
        "recipient_id": payment.recipient_id,
        "reference": payment.reference,
        "beneficiary_receives": {
            "amount_minor": receives.amount_minor,
            "currency": receives.currency,
        },
        "shortfall_foreign_minor": result["shortfall_foreign_minor"],
        "rate": result["provider_rate"],
        "charge_code": result["charge_code"],
        "total_cost_bdt_minor": result["total_cost_bdt_minor"],
        "parent_pays_bdt_minor": result["parent_pays_bdt_minor"],
        "latest_send_date": latest.isoformat() if latest else None,
        "quote_expires_at": iso_utc(quote.expires_at),
        "display": {
            "beneficiary_receives": receives.format(),
            "total_cost": result["display"]["total_cost"],
            "parent_pays": result["display"]["parent_pays"],
            "cost_pct": result["display"]["cost_pct"],
        },
        "disclaimer": SUMMARY_DISCLAIMER,
    }


def dhaka_day_bounds_utc(now: datetime) -> tuple[datetime, datetime]:
    local_day = now.astimezone(DHAKA).date()
    start = datetime.combine(local_day, time.min, tzinfo=DHAKA)
    return start.astimezone(now.tzinfo), (start + timedelta(days=1)).astimezone(now.tzinfo)


class PaymentService:
    def __init__(
        self,
        clock: Clock,
        audit: AuditService,
        recipients: RecipientService,
        quotes: QuoteService,
        kyc: KycService,
        providers: ProviderRegistry,
    ) -> None:
        self._clock = clock
        self._audit = audit
        self._recipients = recipients
        self._quotes = quotes
        self._kyc = kyc
        self._providers = providers

    # --- loading and read-only helpers ---------------------------------------------------
    def load(self, session: Session, actor: Actor, payment_id: str) -> Payment:
        row = session.get(Payment, payment_id)
        if row is None or not actor.can_see_owner(row.owner_id):
            raise errors.NotFound("Payment not found.")
        return row

    @staticmethod
    def result_for(quote: Quote, provider_id: str) -> dict[str, Any]:
        for result in quote.results_json["results"]:
            if result["provider_id"] == provider_id:
                return result
        raise errors.ValidationFailed("That provider is not part of this quote.")

    def _used_today_usd(self, session: Session, payment: Payment, now: datetime) -> int:
        start, end = dhaka_day_bounds_utc(now)
        total = session.execute(
            select(func.coalesce(func.sum(Payment.usd_equivalent_minor), 0)).where(
                Payment.owner_id == payment.owner_id,
                Payment.id != payment.id,
                Payment.state.in_(COUNTS_TOWARD_DAILY_CAP),
                Payment.committed_at >= start,
                Payment.committed_at < end,
            )
        ).scalar_one()
        return int(total)

    def _guard_context(
        self,
        session: Session,
        rules: Rules,
        payment: Payment,
        *,
        mfa_valid: bool = False,
        summary_matches: bool = True,
    ) -> GuardContext:
        now = self._clock.now()
        quote = session.get(Quote, payment.quote_id)
        owner = session.get(User, payment.owner_id)
        recipient = session.get(Recipient, payment.recipient_id)
        if quote is None or owner is None or recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        used_today = self._used_today_usd(session, payment, now)
        return GuardContext(
            now=now,
            quote_expires_at=quote.expires_at,
            kyc_verified=owner.kyc_status == "VERIFIED",
            recipient_allowlisted=recipient.allowlisted,
            sanctions_clear=not is_sanctions_hit(rules, recipient.display_name),
            limit_error=evaluate_limits(rules, payment.usd_equivalent_minor, used_today),
            mfa_valid=mfa_valid,
            summary_matches=summary_matches,
        )

    def blockers(self, session: Session, rules: Rules, payment: Payment) -> list[dict[str, str]]:
        """What would stop this payment right now. Read-only; the UI uses it to disable buttons."""
        open_states = (PaymentState.DRAFT, PaymentState.QUOTED, PaymentState.PENDING_APPROVAL)
        if payment.state not in {s.value for s in open_states}:
            return []
        ctx = self._guard_context(session, rules, payment, mfa_valid=True)
        expired = ctx.quote_expires_at is None or ctx.now >= ctx.quote_expires_at
        checks = [
            (expired, "QUOTE_EXPIRED", "The quote expired. Get a new quote."),
            (not ctx.kyc_verified, "KYC_NOT_VERIFIED", "KYC is not verified (simulated)."),
            (not ctx.recipient_allowlisted, "RECIPIENT_NOT_ALLOWLISTED", "Allowlist the recipient (MFA)."),
            (not ctx.sanctions_clear, "SANCTIONS_HIT", "The recipient matched the mock sanctions screening."),
            (ctx.limit_error is not None, "LIMIT_EXCEEDED", "A sandbox cap would be exceeded. Indicative. Confirm with your AD bank."),
        ]  # fmt: skip
        return [{"code": code, "message": msg} for failed, code, msg in checks if failed]

    # --- the one place a state changes ----------------------------------------------------
    def _apply(
        self,
        session: Session,
        payment: Payment,
        event: Event,
        actor: Actor,
        *,
        action: str,
        decision: Decision | None = None,
        reason_code: str | None = None,
        note: str | None = None,
    ) -> None:
        """Change state and write the history row and ONE audit event in this transaction."""
        old = PaymentState(payment.state)
        new = next_state(old, event, actor.kind)
        now = self._clock.now()
        quote = session.get(Quote, payment.quote_id)
        payment.state = new.value
        payment.updated_at = now
        session.add(
            PaymentTransition(
                payment_id=payment.id,
                from_state=old.value,
                to_state=new.value,
                event=event.value,
                at=now,
                actor_type=actor.audit_type.value,
                actor_id=actor.user_id,
                note=note,
            )
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action=action,
            payment_id=payment.id,
            quote_id=payment.quote_id,
            amount_minor=quote.target_amount_minor if quote else None,
            currency=quote.target_currency if quote else None,
            recipient_id=payment.recipient_id,
            decision=decision,
            reason_code=reason_code,
            detail=f"{old.value}>{new.value} via {event.value}",
        )
        try:
            session.flush()
        except StaleDataError as exc:
            raise errors.InvalidState("The payment was changed by another request.") from exc

    def _quote_only_context(self, quote: Quote) -> GuardContext:
        return GuardContext(self._clock.now(), quote.expires_at, True, True, True, None, True, True)

    def _expire_quote(self, session: Session, payment: Payment) -> None:
        self._apply(
            session,
            payment,
            Event.QUOTE_EXPIRED,
            SYSTEM_ACTOR,
            action="payment.state_changed",
            reason_code="QUOTE_EXPIRED",
            note="Quote expired. Request a new quote.",
        )
        payment.summary_json = None
        payment.summary_hash = None
        payment.committed_at = None
        payment.latest_send_date = None

    def expire_stale_quotes(self, session: Session) -> int:
        """System sweep: QUOTED / PENDING_APPROVAL payments whose quote ran out go back to DRAFT."""
        now = self._clock.now()
        open_states = (PaymentState.QUOTED.value, PaymentState.PENDING_APPROVAL.value)
        stale = (
            session.execute(
                select(Payment)
                .join(Quote, Quote.id == Payment.quote_id)
                .where(Payment.state.in_(open_states), Quote.expires_at <= now)
            )
            .scalars()
            .all()
        )
        for payment in stale:
            self._expire_quote(session, payment)
        return len(stale)

    # --- creating a draft ------------------------------------------------------------------
    def create(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        *,
        quote_id: str,
        provider_id: str,
        recipient_id: str,
        reference: str,
        due_date: Any = None,
    ) -> Payment:
        authorize(actor, Perm.PAYMENT_CREATE_DRAFT)
        quote = self._quotes.get_owned(session, actor, quote_id)
        now = self._clock.now()
        if quote.expires_at <= now:
            raise errors.QuoteExpired("Request a new quote before creating a draft.")
        self.result_for(quote, provider_id)
        recipient = self._recipients.get_owned(session, actor, recipient_id)
        if recipient.country != quote.destination_country:
            raise errors.ValidationFailed("The recipient is in a different country than the quote.")
        if quote.recipient_id and quote.recipient_id != recipient.id:
            raise errors.ValidationFailed("The quote was requested for a different recipient.")
        reference = reference.strip()
        if not is_valid_swift_reference(reference):
            raise errors.ValidationFailed(
                "The reference may use letters, digits and / - ? : ( ) . , + and spaces (max 140)."
            )
        target = Money(quote.target_amount_minor, quote.target_currency)
        payment = Payment(
            id=new_id("pay"),
            owner_id=quote.owner_id,
            created_by=actor.user_id,
            quote_id=quote.id,
            provider_id=provider_id,
            recipient_id=recipient.id,
            state=PaymentState.DRAFT.value,
            reference=reference,
            due_date=due_date or quote.due_date,
            usd_equivalent_minor=usd_equivalent_minor(rules, target),
            created_at=now,
            updated_at=now,
        )
        session.add(payment)
        session.flush()
        session.add(
            PaymentTransition(
                payment_id=payment.id,
                from_state=None,
                to_state=PaymentState.DRAFT.value,
                event="created",
                at=now,
                actor_type=actor.audit_type.value,
                actor_id=actor.user_id,
                note="Draft created",
            )
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="payment.created",
            payment_id=payment.id,
            quote_id=quote.id,
            amount_minor=target.amount_minor,
            currency=target.currency,
            recipient_id=recipient.id,
            decision=Decision.SUGGESTED if actor.audit_type.value == "ai" else None,
            detail=f"DRAFT via {provider_id}",
        )
        check_guards(Event.QUOTE_ATTACHED, self._quote_only_context(quote))
        self._apply(
            session, payment, Event.QUOTE_ATTACHED, actor,
            action="payment.state_changed", note="Quote attached",
        )  # fmt: skip
        return payment

    def requote(
        self, session: Session, actor: Actor, payment_id: str, *, quote_id: str, provider_id: str
    ) -> Payment:
        """Attach a fresh quote to a DRAFT whose earlier quote expired."""
        authorize(actor, Perm.PAYMENT_CREATE_DRAFT)
        payment = self.load(session, actor, payment_id)
        new_quote = self._quotes.get_owned(session, actor, quote_id)
        old_quote = session.get(Quote, payment.quote_id)
        next_state(PaymentState(payment.state), Event.QUOTE_ATTACHED, actor.kind)

        def shape(q: Quote | None) -> tuple[Any, ...]:
            if q is None:
                return ()
            return (q.target_amount_minor, q.target_currency, q.destination_country, q.purpose)

        if shape(old_quote) != shape(new_quote):
            raise errors.ValidationFailed(
                "The new quote must have the same amount, currency, country and purpose."
            )
        self.result_for(new_quote, provider_id)
        check_guards(Event.QUOTE_ATTACHED, self._quote_only_context(new_quote))
        payment.quote_id = new_quote.id
        payment.provider_id = provider_id
        self._apply(
            session, payment, Event.QUOTE_ATTACHED, actor,
            action="payment.state_changed", reason_code="REQUOTED", note="New quote attached",
        )  # fmt: skip
        return payment

    # --- guards, approval ------------------------------------------------------------------
    def _audit_blocked(
        self, session: Session, actor: Actor, payment: Payment, err: errors.ApiError
    ) -> None:
        quote = session.get(Quote, payment.quote_id)
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="compliance.blocked" if err.code in COMPLIANCE_CODES else "approval.blocked",
            payment_id=payment.id,
            quote_id=payment.quote_id,
            amount_minor=quote.target_amount_minor if quote else None,
            currency=quote.target_currency if quote else None,
            recipient_id=payment.recipient_id,
            decision=Decision.BLOCKED,
            reason_code=str(err.extra.get("limit") or err.code),
            detail=err.code,
        )

    def _run_guards(
        self, session: Session, payment: Payment, actor: Actor, event: Event, ctx: GuardContext
    ) -> None:
        try:
            check_guards(event, ctx)
        except errors.QuoteExpired:
            open_states = (PaymentState.QUOTED.value, PaymentState.PENDING_APPROVAL.value)
            if payment.state in open_states:
                self._expire_quote(session, payment)
            raise errors.QuoteExpired(
                "The quote expired and the payment went back to DRAFT. Request a new quote.",
                persist=True,
            ) from None
        except errors.ApiError as err:
            if err.persist:
                self._audit_blocked(session, actor, payment, err)
            raise

    @staticmethod
    def _latest_send_date(rules: Rules, quote: Quote, payment: Payment, now: datetime) -> Any:
        if payment.due_date is None:
            return None
        plan = plan_deadline(
            due_date=payment.due_date,
            now=now,
            calendars=rules.calendars(quote.destination_country),
            params=rules.planner_params(),
        )
        return plan.latest_send_date

    def _live_summary(self, session: Session, payment: Payment) -> dict[str, Any]:
        quote = session.get(Quote, payment.quote_id)
        recipient = session.get(Recipient, payment.recipient_id)
        if quote is None or recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        result = self.result_for(quote, payment.provider_id)
        return build_summary(payment, quote, result, self._recipients.label(recipient))

    def request_approval(
        self, session: Session, actor: Actor, rules: Rules, payment_id: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.PAYMENT_REQUEST_APPROVAL)
        payment = self.load(session, actor, payment_id)
        self._kyc.complete_due_reviews(session)
        next_state(PaymentState(payment.state), Event.REQUEST_APPROVAL, actor.kind)
        ctx = self._guard_context(session, rules, payment, mfa_valid=True)
        self._run_guards(session, payment, actor, Event.REQUEST_APPROVAL, ctx)
        quote = session.get(Quote, payment.quote_id)
        assert quote is not None  # FK guarantees it
        now = self._clock.now()
        payment.latest_send_date = self._latest_send_date(rules, quote, payment, now)
        summary = self._live_summary(session, payment)
        payment.summary_json = summary
        payment.summary_hash = hash_object(summary)
        payment.committed_at = now
        self._apply(
            session, payment, Event.REQUEST_APPROVAL, actor,
            action="approval.requested",
            decision=Decision.SUGGESTED if actor.audit_type.value == "ai" else None,
            note="Approval requested",
        )  # fmt: skip
        return {
            "payment_id": payment.id,
            "state": payment.state,
            "summary": summary,
            "summary_hash": payment.summary_hash,
        }

    def approve(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        payment_id: str,
        *,
        confirm_hash: str,
        mfa_proof_raw: str | None,
    ) -> dict[str, Any]:
        try:
            authorize(actor, Perm.PAYMENT_APPROVE)
        except errors.AiCannotApprove:
            self._audit.append(
                session,
                actor_type=actor.audit_type,
                actor_id=actor.user_id,
                action="approval.blocked",
                payment_id=payment_id,
                decision=Decision.BLOCKED,
                reason_code="AI_CANNOT_APPROVE",
            )
            raise errors.AiCannotApprove(
                "The AI assistant can never approve a payment. A human must do it in the app.",
                persist=True,
            ) from None
        payment = self.load(session, actor, payment_id)
        self._kyc.complete_due_reviews(session)
        next_state(PaymentState(payment.state), Event.APPROVE, actor.kind)
        now = self._clock.now()
        proof = auth.find_valid_mfa_proof(
            session,
            raw=mfa_proof_raw,
            user_id=actor.user_id,
            scope="approve_payment",
            subject_id=payment.id,
            now=now,
        )
        stored = payment.summary_hash
        live = hash_object(self._live_summary(session, payment))
        matches = bool(stored) and confirm_hash == stored and live == stored
        ctx = self._guard_context(
            session, rules, payment, mfa_valid=proof is not None, summary_matches=matches
        )
        self._run_guards(session, payment, actor, Event.APPROVE, ctx)
        assert proof is not None  # the FRESH_MFA guard passed
        proof.used_at = now
        payment.approved_by = actor.user_id
        payment.approved_at = now
        self._apply(
            session, payment, Event.APPROVE, actor,
            action="approval.granted",
            decision=Decision.APPROVED,
            reason_code=auth.proof_reference(proof),
            note="Approved by the parent",
        )  # fmt: skip
        return {
            "payment_id": payment.id,
            "state": payment.state,
            "approved_by": payment.approved_by,
            "approved_at": iso_utc(now),
        }

    # --- reject, cancel, submit, provider events ------------------------------------------
    def reject(
        self, session: Session, actor: Actor, payment_id: str, reason: str | None = None
    ) -> Payment:
        authorize(actor, Perm.PAYMENT_REJECT)
        payment = self.load(session, actor, payment_id)
        self._apply(
            session, payment, Event.REJECT, actor,
            action="approval.rejected",
            decision=Decision.REJECTED,
            reason_code="REJECTED_BY_" + actor.kind.value.upper(),
            note=(reason or "Rejected")[:200],
        )  # fmt: skip
        return payment

    def cancel(self, session: Session, actor: Actor, payment_id: str) -> Payment:
        authorize(actor, Perm.PAYMENT_CANCEL)
        payment = self.load(session, actor, payment_id)
        self._apply(
            session, payment, Event.CANCEL, actor,
            action="payment.state_changed",
            reason_code="CANCELLED_BY_USER",
            note="Cancelled before submission",
        )  # fmt: skip
        return payment

    def due_for_submission(self, session: Session, delay_seconds: int) -> list[str]:
        cutoff = self._clock.now() - timedelta(seconds=delay_seconds)
        rows = session.execute(
            select(Payment.id).where(
                Payment.state == PaymentState.APPROVED.value, Payment.approved_at <= cutoff
            )
        )
        return [row[0] for row in rows]

    def submit(self, session: Session, rules: Rules, payment_id: str) -> Payment:
        """System step: assign a UETR, hand the instruction to the (mock) provider."""
        payment = session.get(Payment, payment_id)
        if payment is None:
            raise errors.NotFound("Payment not found.")
        next_state(PaymentState(payment.state), Event.SUBMIT, SYSTEM_ACTOR.kind)
        quote = session.get(Quote, payment.quote_id)
        recipient = session.get(Recipient, payment.recipient_id)
        if quote is None or recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        now = self._clock.now()
        uetr = new_uetr()
        result = self.result_for(quote, payment.provider_id)
        instruction = SubmitInstruction(
            payment_id=payment.id,
            uetr=uetr,
            amount=Money(quote.target_amount_minor, quote.target_currency),
            charge_code=ChargeCode(result["charge_code"]),
            beneficiary_name=recipient.display_name,
            beneficiary_account_masked=self._recipients.account_mask(recipient),
            remittance=payment.reference,
            scenario=scenario_for(rules, recipient.display_name),
        )
        self._providers.get(rules, payment.provider_id).submit(session, instruction, now)
        payment.uetr = uetr
        payment.submitted_at = now
        self._apply(
            session, payment, Event.SUBMIT, SYSTEM_ACTOR,
            action="payment.state_changed",
            reason_code="SUBMITTED_SIMULATED",
            note="Instruction sent (simulated)",
        )  # fmt: skip
        return payment

    def apply_provider_event(
        self, session: Session, *, provider_id: str, event: str, payment_id: str, uetr: str
    ) -> Payment:
        """A verified webhook from a provider settles or fails a SUBMITTED payment."""
        payment = session.get(Payment, payment_id)
        if payment is None:
            raise errors.NotFound("Payment not found.")
        if payment.provider_id != provider_id or payment.uetr != uetr:
            raise errors.ValidationFailed("The webhook does not match this payment.")
        actor = provider_actor(provider_id)
        now = self._clock.now()
        if event == "payment.settled":
            self._apply(
                session, payment, Event.PROVIDER_SETTLED, actor,
                action="payment.state_changed", reason_code="PROVIDER_SETTLED",
                note="Credited (simulated)",
            )  # fmt: skip
            payment.settled_at = now
        elif event == "payment.failed":
            self._apply(
                session, payment, Event.PROVIDER_FAILED, actor,
                action="payment.state_changed", reason_code="PROVIDER_FAILED",
                note="Failed: rejected by the provider (simulated)",
            )  # fmt: skip
            payment.failure_reason = "Rejected by the provider (simulated)"
        else:
            raise errors.ValidationFailed(f"Unknown webhook event: {event[:40]}")
        return payment

    # --- views -----------------------------------------------------------------------------
    def brief(self, session: Session, payment: Payment) -> dict[str, Any]:
        quote = session.get(Quote, payment.quote_id)
        recipient = session.get(Recipient, payment.recipient_id)
        if quote is None or recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        result = self.result_for(quote, payment.provider_id)
        return {
            "payment_id": payment.id,
            "state": payment.state,
            "target": Money(quote.target_amount_minor, quote.target_currency).to_dict(),
            "provider_id": payment.provider_id,
            "provider_name": result["provider_name"],
            "recipient_label": self._recipients.label(recipient),
            "reference": payment.reference,
            "due_date": payment.due_date.isoformat() if payment.due_date else None,
            "uetr": payment.uetr,
            "parent_pays": result["display"]["parent_pays"],
            "created_at": iso_utc(payment.created_at),
            "updated_at": iso_utc(payment.updated_at),
        }

    def view(self, session: Session, rules: Rules, payment: Payment) -> dict[str, Any]:
        quote = session.get(Quote, payment.quote_id)
        recipient = session.get(Recipient, payment.recipient_id)
        if quote is None or recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        state = PaymentState(payment.state)
        blockers = self.blockers(session, rules, payment)
        now = self._clock.now()
        body = self.brief(session, payment)
        body.update(
            {
                "quote_id": quote.id,
                "quote_expires_at": iso_utc(quote.expires_at),
                "quote_status": "EXPIRED" if quote.expires_at <= now else "ACTIVE",
                "destination_country": quote.destination_country,
                "purpose": quote.purpose,
                "recipient": {
                    "recipient_id": recipient.id,
                    "label": self._recipients.label(recipient),
                    "allowlisted": recipient.allowlisted,
                },
                "result": self.result_for(quote, payment.provider_id),
                "latest_send_date": payment.latest_send_date.isoformat()
                if payment.latest_send_date
                else None,
                "summary": payment.summary_json,
                "summary_hash": payment.summary_hash,
                "summary_preview": self._live_summary(session, payment)
                if state is PaymentState.QUOTED
                else None,
                "approved_by": payment.approved_by,
                "approved_at": iso_utc(payment.approved_at) if payment.approved_at else None,
                "submitted_at": iso_utc(payment.submitted_at) if payment.submitted_at else None,
                "settled_at": iso_utc(payment.settled_at) if payment.settled_at else None,
                "failure_reason": payment.failure_reason,
                "readiness": {
                    "blockers": blockers,
                    "can_request_approval": state is PaymentState.QUOTED and not blockers,
                    "can_approve": state is PaymentState.PENDING_APPROVAL and not blockers,
                },
                "simulated": True,
                "disclaimer": SUMMARY_DISCLAIMER,
            }
        )
        return body

    def list(
        self, session: Session, actor: Actor, limit: int, cursor: str | None
    ) -> tuple[list[Payment], str | None]:
        authorize(actor, Perm.PAYMENT_READ)
        stmt = select(Payment).order_by(Payment.created_at.desc(), Payment.id.desc())
        if actor.owner_id is not None:
            stmt = stmt.where(Payment.owner_id == actor.owner_id)
        if cursor:
            try:
                stamp, _, last_id = cursor.partition("~")
                last_at = datetime.fromisoformat(stamp)
            except ValueError as exc:
                raise errors.BadRequest("The cursor is not valid.") from exc
            stmt = stmt.where(
                (Payment.created_at < last_at)
                | ((Payment.created_at == last_at) & (Payment.id < last_id))
            )
        rows = list(session.execute(stmt.limit(limit + 1)).scalars())
        page = rows[:limit]
        next_cursor = None
        if len(rows) > limit and page:
            next_cursor = f"{page[-1].created_at.isoformat()}~{page[-1].id}"
        return page, next_cursor

    def tracker(
        self, session: Session, actor: Actor, rules: Rules, payment_id: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.PAYMENT_READ)
        payment = self.load(session, actor, payment_id)
        quote = session.get(Quote, payment.quote_id)
        host_rail = rules.corridor(quote.destination_country).host_rail if quote else ""
        steps = session.execute(
            select(PaymentTransition)
            .where(PaymentTransition.payment_id == payment.id)
            .order_by(PaymentTransition.id)
        ).scalars()
        return {
            "payment_id": payment.id,
            "uetr": payment.uetr,
            "state": payment.state,
            "timeline": [
                {
                    "state": t.to_state,
                    "at": iso_utc(t.at),
                    "note": t.note,
                    "actor_type": t.actor_type,
                }
                for t in steps
            ],
            "host_rail": f"{host_rail} (named only: the sandbox does not simulate it)",
            "simulated": True,
        }

    def instruction_preview(
        self, session: Session, actor: Actor, payment_id: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.PAYMENT_READ)
        payment = self.load(session, actor, payment_id)
        quote = session.get(Quote, payment.quote_id)
        recipient = session.get(Recipient, payment.recipient_id)
        owner = session.get(User, payment.owner_id)
        if quote is None or recipient is None or owner is None:
            raise errors.InvalidState("The payment references missing data.")
        result = self.result_for(quote, payment.provider_id)
        return build_instruction_preview(
            payment_id=payment.id,
            uetr=payment.uetr,
            value_date=payment.due_date,
            amount=Money(quote.target_amount_minor, quote.target_currency),
            ordering_name=owner.display_name,
            ordering_address=owner.address,
            receiving_bic=recipient.bic,
            beneficiary_name=recipient.display_name,
            beneficiary_account_masked=self._recipients.account_mask(recipient),
            remittance=payment.reference,
            charge_code=ChargeCode(result["charge_code"]),
        )
