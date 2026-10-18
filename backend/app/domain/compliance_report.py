"""Payment compliance report: an evidence pack for one payment, in a form a reviewer can check.

It collects, from records the system already keeps: who the originator and beneficiary are (the
travel rule), every control that guards a payment with its result and evidence, the approval
proof, the state timeline, the payment's slice of the audit log and the verification of the whole
chain. A hash of the finished report lets anyone detect an edited copy. Reading it changes
nothing. Everything in it is synthetic.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.audit.service import AuditService, event_dict
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import hash_object
from app.domain.compliance import is_sanctions_hit
from app.domain.payments import PaymentService
from app.domain.rbac import Actor, Perm, authorize
from app.domain.recipients import RecipientService
from app.domain.rules import Rules
from app.models import AuditEvent, Payment, Recipient, User

DISCLAIMER = "Sandbox. Synthetic data. No real money moved. Indicative. Confirm with your AD bank."
CAP_LABEL = "Sandbox cap (our own, not a legal limit)"


def _control(key: str, label: str, result: str, evidence: str) -> dict[str, str]:
    return {"key": key, "label": label, "result": result, "evidence": evidence}


class ReportService:
    def __init__(
        self,
        clock: Clock,
        audit: AuditService,
        payments: PaymentService,
        recipients: RecipientService,
    ) -> None:
        self._clock = clock
        self._audit = audit
        self._payments = payments
        self._recipients = recipients

    def payment_report(
        self, session: Session, actor: Actor, rules: Rules, payment_id: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.AUDIT_READ)
        payment = self._payments.load(session, actor, payment_id)  # 404 for someone else's
        view = self._payments.view(session, rules, payment)
        recipient = session.get(Recipient, payment.recipient_id)
        owner = session.get(User, payment.owner_id)
        if recipient is None or owner is None:
            raise errors.InvalidState("The payment references missing data.")
        events = self._events(session, payment)
        chain = self._audit.verify(session).to_api_dict()
        result = view["result"]
        display = result["display"]
        body: dict[str, Any] = {
            "report_type": "payment_compliance_report",
            "generated_at": iso_utc(self._clock.now()),
            "synthetic": True,
            "disclaimer": DISCLAIMER,
            "payment": {
                "payment_id": payment.id,
                "state": payment.state,
                "reference": payment.reference,
                "provider_name": view["provider_name"],
                "uetr": payment.uetr,
                "due_date": view["due_date"],
                "latest_send_date": view["latest_send_date"],
                "created_at": view["created_at"],
                "approved_at": view["approved_at"],
                "submitted_at": view["submitted_at"],
                "settled_at": view["settled_at"],
                "failure_reason": payment.failure_reason,
            },
            "amount": {
                "beneficiary_receives": view["target"]["formatted"],
                "rate": result["provider_rate"],
                "charge_code": result["charge_code"],
                "total_cost": display["total_cost"],
                "cost_pct": display["cost_pct"],
                "parent_pays": display["parent_pays"],
                "shortfall": display["shortfall"],
            },
            "parties": {
                "originator": {
                    "name": owner.display_name,
                    "address": owner.address,
                    "country": "BD",
                },
                "beneficiary": {
                    "name": recipient.display_name,
                    "account_masked": self._recipients.account_mask(recipient),
                    "bic": recipient.bic,
                    "country": recipient.country,
                },
            },
            "approval": self._approval(payment, events),
            "controls": self._controls(session, rules, payment, recipient, events, chain, view),
            "timeline": self._payments.tracker(session, actor, rules, payment.id)["timeline"],
            "audit": {"events": events, "chain": chain},
        }
        body["report_hash"] = hash_object(body)
        return body

    # --- parts -----------------------------------------------------------------------------
    @staticmethod
    def _events(session: Session, payment: Payment) -> list[dict[str, Any]]:
        rows = session.execute(
            select(AuditEvent)
            .where(
                or_(
                    AuditEvent.payment_id == payment.id,
                    and_(
                        AuditEvent.quote_id == payment.quote_id,
                        AuditEvent.action == "quote.created",
                    ),
                )
            )
            .order_by(AuditEvent.seq)
        ).scalars()
        return [event_dict(row) for row in rows]

    @staticmethod
    def _approval(payment: Payment, events: list[dict[str, Any]]) -> dict[str, Any]:
        granted = next((e for e in events if e["action"] == "approval.granted"), None)
        return {
            "approved": payment.approved_at is not None,
            "approved_by": payment.approved_by,
            "approved_at": iso_utc(payment.approved_at) if payment.approved_at else None,
            "summary_hash": payment.summary_hash,
            "mfa_proof_reference": granted["reason_code"] if granted else None,
        }

    def _controls(
        self,
        session: Session,
        rules: Rules,
        payment: Payment,
        recipient: Recipient,
        events: list[dict[str, Any]],
        chain: dict[str, Any],
        view: dict[str, Any],
    ) -> list[dict[str, str]]:
        approved = payment.approved_at is not None
        granted = next((e for e in events if e["action"] == "approval.granted"), None)
        webhook = next((e for e in events if e["action"] == "webhook.accepted"), None)
        readiness = view["readiness"]
        owner = session.get(User, payment.owner_id)
        kyc = owner.kyc_status if owner else "UNKNOWN"
        blockers = {b["code"] for b in readiness["blockers"]}
        out = [
            _control(
                "kyc", "Identity check (KYC, simulated)",
                "PASS" if kyc == "VERIFIED" else "PENDING",
                f"Mock KYC status is {kyc}. Approval is refused unless it is VERIFIED.",
            ),
            _control(
                "allowlist", "Recipient allowlisted with MFA",
                "PASS" if recipient.allowlisted else "PENDING",
                (
                    f"Allowlisted by {recipient.allowlisted_by} on "
                    f"{iso_utc(recipient.allowlisted_at) if recipient.allowlisted_at else 'an earlier date'}."
                    if recipient.allowlisted
                    else "The recipient is not allowlisted yet."
                ),
            ),
        ]  # fmt: skip
        hit = is_sanctions_hit(rules, recipient.display_name)
        out.append(
            _control(
                "sanctions", "Sanctions screening (mock)",
                "BLOCKED" if hit else "PASS",
                "The recipient matched the mock screening." if hit
                else "The recipient name did not match the mock screening. It uses a test token, not a real list.",
            )
        )  # fmt: skip
        if approved:
            caps = (
                "PASS",
                "Checked at approval against the sandbox per-transaction and daily caps. They are our own choice, not a legal limit.",
            )
        elif "LIMIT_EXCEEDED" in blockers:
            caps = (
                "BLOCKED",
                "A sandbox cap would be exceeded. The caps are our own choice, not a legal limit.",
            )
        else:
            caps = (
                "PASS",
                "Below the sandbox caps now. They are our own choice, not a legal limit.",
            )
        out.append(_control("caps", CAP_LABEL, caps[0], caps[1]))  # fmt: skip
        out.append(
            _control(
                "mfa", "Fresh MFA at approval",
                "PASS" if granted else "NOT_YET",
                f"Proof {granted['reason_code']}, valid five minutes, single use, bound to this payment."
                if granted else "Not approved yet.",
            )
        )  # fmt: skip
        if approved and payment.summary_hash:
            out.append(_control("summary_hash", "Approval bound to the summary the human saw", "PASS",
                                f"The approval confirmed {payment.summary_hash}."))  # fmt: skip
        elif payment.summary_hash:
            out.append(_control("summary_hash", "Approval bound to the summary the human saw", "PENDING",
                                f"Summary frozen as {payment.summary_hash}; waiting for approval."))  # fmt: skip
        else:
            out.append(_control("summary_hash", "Approval bound to the summary the human saw", "NOT_YET",
                                "Approval has not been requested."))  # fmt: skip
        human = granted is not None and granted["actor_type"] == "user"
        out.append(
            _control(
                "human_approval", "Approved by a human, not the AI",
                "PASS" if human else "NOT_YET",
                f"Approved by user {payment.approved_by}. The AI service account cannot approve."
                if human else "Not approved yet. Only a human parent can approve.",
            )
        )  # fmt: skip
        out.append(
            _control("travel_rule", "Originator and beneficiary data (travel rule)", "PASS",
                     "Both parties are listed in this report and in the payment instruction preview.")
        )  # fmt: skip
        if webhook is not None and payment.state in {"SETTLED", "FAILED"}:
            provider = (
                "PASS",
                "A provider webhook with a valid HMAC signature was accepted (simulated provider).",
            )
        elif payment.state == "SUBMITTED":
            provider = ("PENDING", "Waiting for the simulated provider's signed webhook.")
        else:
            provider = ("NOT_YET", "The payment has not been submitted.")
        out.append(
            _control(
                "provider_confirmation", "Provider status confirmed by signed webhook", *provider
            )
        )
        out.append(
            _control(
                "audit_chain", "Audit log hash chain verified", "PASS" if chain["status"] == "PASS" else "FAIL",
                f"{chain['events_checked']} events checked; head is event {chain['head']['seq']}."
                if chain["status"] == "PASS" else f"Chain failed at event {chain['failed_seq']}.",
            )
        )  # fmt: skip
        return out
