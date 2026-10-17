"""The sandbox bank's review desk: a quick yes, no or ask-for-more on payments that need a person.

Most payments have no reason to wait for anyone and go through the fast lane. A payment with a
signal (see ``app.engine.risk_signals``) opens a review. A reviewer, who is a human with a fresh MFA
proof, sees one page with the facts, the signals and what to ask, and answers CLEAR, ASK_INFO or
DECLINE. A clock shows how long the review has waited, and the parent can send a reminder.

What this is not: it is not anti-money-laundering screening and it never says a payment is legal or
illegal. It orders and explains; a person decides; the AI can only explain and can never decide.
Everything is synthetic and labelled so.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.risk.scorer import RiskScorer
from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import FieldCipher
from app.core.ids import new_id
from app.domain import auth
from app.domain.constants import Decision, PaymentState, ReviewDecision, ReviewStatus
from app.domain.payments import COUNTS_TOWARD_DAILY_CAP, PaymentService
from app.domain.rbac import Actor, Perm, authorize
from app.domain.recipients import RecipientService
from app.domain.review_text import (
    FACTOR_TEXT,
    GLOSSARY,
    PERSON_FIRST,
    PERSON_KNOWN,
    REASON_TEXT,
    SIGNAL_TEXT,
    STATUS_TEXT,
)
from app.domain.rules import Rules
from app.engine import risk_signals as rs
from app.engine.money import Money
from app.models import BankReview, Document, Payment, Quote, Recipient, User

DISCLAIMER = (
    "Sandbox. Synthetic data. A person at the bank decides. Indicative. Confirm with your AD bank."
)
INVOICE_KINDS = ("fee_demand_note",)
WAITING = (ReviewStatus.OPEN.value, ReviewStatus.INFO_REQUESTED.value)
MIN_NOTE = 5
MAX_TEXT = 500


def _plain(value: str, limit: int = MAX_TEXT) -> str:
    return " ".join(value.split())[:limit]


class BankReviewService:
    def __init__(
        self,
        clock: Clock,
        audit: AuditService,
        payments: PaymentService,
        recipients: RecipientService,
        cipher: FieldCipher,
        scorer: RiskScorer | None = None,
    ) -> None:
        self._cipher = cipher
        self._clock = clock
        self._audit = audit
        self._payments = payments
        self._recipients = recipients
        self._scorer = scorer

    # --- opening a review (called when approval is requested) ---------------------------------
    def _facts(
        self, session: Session, rules: Rules, payment: Payment, now: datetime
    ) -> rs.ReviewFacts:
        recipient = session.get(Recipient, payment.recipient_id)
        if recipient is None:
            raise errors.InvalidState("The payment references missing data.")
        window_start = now - timedelta(days=rules.review_split_window_days)
        earlier = session.execute(
            select(Payment.usd_equivalent_minor).where(
                Payment.owner_id == payment.owner_id,
                Payment.id != payment.id,
                Payment.state.in_(COUNTS_TOWARD_DAILY_CAP),
                Payment.committed_at >= window_start,
            )
        ).scalars()
        paid_before = session.execute(
            select(func.count()).where(
                Payment.recipient_id == payment.recipient_id,
                Payment.id != payment.id,
                Payment.state.in_(COUNTS_TOWARD_DAILY_CAP),
            )
        ).scalar_one()
        invoice = session.execute(
            select(func.count()).where(
                Document.owner_id == payment.owner_id, Document.kind.in_(INVOICE_KINDS)
            )
        ).scalar_one()
        quote = session.get(Quote, payment.quote_id)
        return rs.ReviewFacts(
            amount_usd_minor=payment.usd_equivalent_minor,
            earlier_usd_minor=tuple(int(v) for v in earlier),
            recipient_first_payment=paid_before == 0,
            recipient_name_flagged=rules.review_test_token.lower()
            in recipient.display_name.lower(),
            has_invoice_on_file=invoice > 0,
            purpose=quote.purpose if quote else "",
        )

    def _priority(self, session: Session, payment: Payment, now: datetime) -> dict[str, Any] | None:
        """The trained model's ordering hint for the queue, or None when it is not loaded.

        It looks only at the size of the payment and at this household's own earlier payments."""
        if self._scorer is None:
            return None
        counted = (Payment.owner_id == payment.owner_id, Payment.id != payment.id)
        states = Payment.state.in_(COUNTS_TOWARD_DAILY_CAP)

        def count(*extra: Any) -> int:
            return int(
                session.execute(select(func.count()).where(*counted, states, *extra)).scalar_one()
            )

        last = session.execute(
            select(func.max(Payment.committed_at)).where(*counted, states)
        ).scalar_one()
        hours = 720.0 if last is None else max(0.0, (now - last).total_seconds() / 3600.0)
        score_facts = {
            "amount": payment.usd_equivalent_minor / 100.0,  # a model input, not money handling
            "currency": "US Dollar",
            "sender_24h": count(Payment.committed_at >= now - timedelta(hours=24)),
            "sender_7d": count(Payment.committed_at >= now - timedelta(days=7)),
            "sender_total": count(),
            "hours_since_last": hours,
            "pair_count": count(Payment.recipient_id == payment.recipient_id),
        }
        return self._scorer.score(score_facts).to_dict()

    @staticmethod
    def _ai_decides(signals: list[rs.Signal], priority: dict[str, Any]) -> list[rs.Signal]:
        """With the model loaded, ITS reading decides who a person must look at.

        The plain rules stay on the page as context (how large, how many), except the name-list
        match, which is a lookup like the sanctions mock and not a risk estimate. The model adds one
        signal, named for what it did, when its band is medium or high."""
        kept = [
            replace(s, needs_human=False) if s.code in (rs.LARGE_AMOUNT, rs.POSSIBLE_SPLIT) else s
            for s in signals
        ]
        if priority["band"] in ("MEDIUM", "HIGH"):
            kept.insert(
                0,
                rs.Signal(
                    "AI_RISK",
                    True,
                    {"band": priority["band"], "percentile": str(priority["percentile"])},
                ),
            )
        return kept

    def open_for(
        self, session: Session, actor: Actor, rules: Rules, payment: Payment
    ) -> BankReview:
        """Work out whether a person must look at this payment and start (or restart) its review."""
        now = self._clock.now()
        facts = self._facts(session, rules, payment, now)
        signals = rs.find_signals(
            facts,
            rs.ReviewParams(
                large_usd_minor=rules.review_large_usd * 100,
                split_min_payments=rules.review_split_min_payments,
                split_window_days=rules.review_split_window_days,
            ),
        )
        priority = self._priority(session, payment, now)
        if priority is not None:
            signals = self._ai_decides(signals, priority)
        if rules.review_bank_authorizes_all and not rs.needs_human(signals):
            signals.insert(0, rs.Signal("BANK_AUTHORIZES_ALL", True))  # the bank's own rule
        human = rs.needs_human(signals)
        status = ReviewStatus.OPEN if human else ReviewStatus.CLEARED_AUTO
        row = session.execute(
            select(BankReview).where(BankReview.payment_id == payment.id)
        ).scalar_one_or_none()
        if row is None:
            row = BankReview(id=new_id("brv"), payment_id=payment.id, owner_id=payment.owner_id)
            session.add(row)
        row.status = status.value
        row.signals_json = {"signals": [s.to_dict() for s in signals]}
        row.priority_json = priority
        row.opened_at = now
        row.due_at = now + timedelta(hours=rules.review_target_hours)
        row.decided_at = row.decided_by = row.reason_code = row.reviewer_note = None
        row.parent_reply = None
        row.reminders, row.last_reminder_at, row.updated_at = 0, None, now
        codes = ",".join(s.code for s in signals) or "none"
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank_review.opened" if human else "bank_review.fast_lane",
            payment_id=payment.id,
            recipient_id=payment.recipient_id,
            reason_code=status.value,
            detail=f"signals={codes} routing={'ai' if priority else 'rules'}"
            + (f" risk={priority['band']}:{priority['percentile']}" if priority else ""),
            model_version=priority["model_id"] if priority else None,
        )
        session.flush()
        return row

    # --- the gate in front of the parent's approval ---------------------------------------------
    def review_of(self, session: Session, payment_id: str) -> BankReview | None:
        return session.execute(
            select(BankReview).where(BankReview.payment_id == payment_id)
        ).scalar_one_or_none()

    def blocker(self, session: Session, payment: Payment) -> dict[str, str] | None:
        row = self.review_of(session, payment.id)
        if row is None or row.status not in WAITING:
            return None
        return {
            "code": "BANK_REVIEW_PENDING",
            "message": STATUS_TEXT[row.status]["headline"]
            + ". "
            + STATUS_TEXT[row.status]["parent"],
        }

    def gate(self, session: Session, payment: Payment) -> None:
        blocker = self.blocker(session, payment)
        if blocker is not None:
            raise errors.BankReviewPending(blocker["message"], persist=False)

    # --- reading ----------------------------------------------------------------------------------
    def _row(self, session: Session, actor: Actor, payment_id: str) -> tuple[Payment, BankReview]:
        authorize(actor, Perm.REVIEW_READ)
        payment = self._payments.load(session, actor, payment_id)  # 404 for someone else's
        row = self.review_of(session, payment.id)
        if row is None:
            raise errors.NotFound("This payment has no bank review yet. Request approval first.")
        return payment, row

    def _clock_view(self, row: BankReview, rules: Rules, now: datetime) -> dict[str, Any]:
        target = rules.review_target_hours * 3600
        if row.status != ReviewStatus.OPEN.value:
            return {
                "running": False,
                "state": "not_running",
                "target_hours": rules.review_target_hours,
            }
        left = (row.due_at - now).total_seconds()
        state = "overdue" if left <= 0 else "due_soon" if left <= 0.25 * target else "on_time"
        return {
            "running": True,
            "state": state,
            "due_at": iso_utc(row.due_at),
            "minutes_left": int(left // 60),
            "waited_minutes": int((now - row.opened_at).total_seconds() // 60),
            "target_hours": rules.review_target_hours,
        }

    def _can_remind(self, row: BankReview, rules: Rules, now: datetime) -> bool:
        if row.status != ReviewStatus.OPEN.value:
            return False
        if row.last_reminder_at is None:
            return True
        return now - row.last_reminder_at >= timedelta(hours=rules.review_reminder_hours)

    @staticmethod
    def _reply_context(row: BankReview) -> str:
        return f"bank_reviews.parent_reply|{row.id}"

    def _seal_reply(self, row: BankReview, text: str) -> str:
        """The parent's words may hold personal details, so they sit encrypted in the database."""
        return self._cipher.encrypt(text, context=self._reply_context(row))

    def _open_reply(self, row: BankReview) -> str | None:
        if row.parent_reply is None:
            return None
        return self._cipher.decrypt(row.parent_reply, context=self._reply_context(row))

    @staticmethod
    def _ai_view(row: BankReview) -> dict[str, Any] | None:
        """The AI's risk score for this payment, in words, or None when the model was not loaded.

        The score is how much more unusual the payment looks than the practice payments (0 to 100).
        A warning is shown only when the band is medium or higher; a low score shows none."""
        reading = row.priority_json
        if not reading:
            return None
        raised = set(reading.get("drivers", []))
        shares = {f["code"]: f["share"] for f in reading.get("factors", [])}
        factors = []
        for code, text in FACTOR_TEXT.items():
            share = shares.get(code)
            if share is None:  # a reading without per-factor shares: only the raised ones are known
                level = "raises" if code in raised else "neutral"
            else:
                level = "raises" if share >= 0.25 else "lowers" if share <= -0.25 else "neutral"
            plain = text[level]
            if code == "PERSON":  # say what is known for certain, not only that it looks unusual
                first = reading.get("population") == "first"
                if level == "raises" and first:
                    plain = PERSON_FIRST
                elif level == "lowers" and not first:
                    plain = PERSON_KNOWN
            factors.append({"code": code, "title": text["title"], "level": level, "plain": plain})
        band = reading["band"]
        return {
            "score": reading["percentile"],
            "band": band,
            "percentile": reading["percentile"],
            "warning": band in ("MEDIUM", "HIGH"),
            "among": "a first payment to this receiver"
            if reading.get("population") == "first"
            else "a repeat payment",
            "factors": factors,
            "drivers": [f for f in factors if f["level"] == "raises" and band != "LOW"],
            "hit_rate": reading.get("hit_rate"),
            "model_id": reading["model_id"],
            "decides_who_a_person_looks_at": True,
        }

    @staticmethod
    def _signals(row: BankReview) -> list[dict[str, Any]]:
        return list(row.signals_json.get("signals", []))

    def view(self, session: Session, actor: Actor, rules: Rules, payment_id: str) -> dict[str, Any]:
        payment, row = self._row(session, actor, payment_id)
        if actor.kind.value == "admin":
            return self._reviewer_view(session, actor, rules, payment, row)
        return self._parent_view(rules, payment, row)

    def _parent_view(self, rules: Rules, payment: Payment, row: BankReview) -> dict[str, Any]:
        now = self._clock.now()
        status = STATUS_TEXT[row.status]
        shown = []
        for signal in self._signals(row):
            text = SIGNAL_TEXT[signal["code"]]
            shown.append(
                {
                    "code": signal["code"],
                    "title": text["title"],
                    "means": text["parent_means"],
                    "why": text["parent_why"],
                    "prepare": text["prepare"],
                    "figures": signal["figures"],
                    "needs_bank_person": signal["needs_human"],
                }
            )
        return {
            "payment_id": payment.id,
            "status": row.status,
            "headline": status["headline"],
            "plain": status["parent"],
            "lane": "fast" if row.status == ReviewStatus.CLEARED_AUTO.value else "reviewed",
            "signals": shown,
            "ai": self._ai_view(row),
            "clock": self._clock_view(row, rules, now),
            "reviewer_asked": row.reviewer_note
            if row.status == ReviewStatus.INFO_REQUESTED.value
            else None,
            "decision_reason": REASON_TEXT.get(row.reason_code or "", None),
            "decision_note": row.reviewer_note
            if row.status == ReviewStatus.DECLINED.value
            else None,
            "your_reply": self._open_reply(row),
            "can_reply": row.status == ReviewStatus.INFO_REQUESTED.value,
            "can_remind": self._can_remind(row, rules, now),
            "reminders_sent": row.reminders,
            "glossary": GLOSSARY,
            "simulated": True,
            "disclaimer": DISCLAIMER,
        }

    def _reviewer_view(
        self, session: Session, actor: Actor, rules: Rules, payment: Payment, row: BankReview
    ) -> dict[str, Any]:
        now = self._clock.now()
        owner = session.get(User, payment.owner_id)
        recipient = session.get(Recipient, payment.recipient_id)
        quote = session.get(Quote, payment.quote_id)
        if owner is None or recipient is None or quote is None:
            raise errors.InvalidState("The payment references missing data.")
        view = self._payments.view(session, rules, payment)
        documents = sorted(
            {
                d.kind
                for d in session.execute(
                    select(Document).where(Document.owner_id == payment.owner_id)
                ).scalars()
            }
        )
        signals = []
        for signal in self._signals(row):
            text = SIGNAL_TEXT[signal["code"]]
            signals.append(
                {
                    "code": signal["code"],
                    "title": text["title"],
                    "needs_human": signal["needs_human"],
                    "figures": signal["figures"],
                    "check": text["reviewer_check"],
                }
            )
        return {
            "payment_id": payment.id,
            "status": row.status,
            "payment_state": payment.state,
            "payer": {"name": owner.display_name, "kyc_status": owner.kyc_status},
            "recipient": {
                "label": self._recipients.label(recipient),
                "allowlisted": recipient.allowlisted,
            },
            "amount": view["target"],
            "purpose": quote.purpose,
            "destination_country": quote.destination_country,
            "reference": payment.reference,
            "provider_name": view["provider_name"],
            "due_date": view["due_date"],
            "documents_on_file": documents,
            "signals": signals,
            "questions": [s["check"] for s in signals],
            "hint": self._hint(signals),
            "priority": row.priority_json,
            "ai": self._ai_view(row),
            "routing": "ai" if row.priority_json else "rules",
            "clock": self._clock_view(row, rules, now),
            "reminders": row.reminders,
            "parent_reply": self._open_reply(row),
            "reviewer_note": row.reviewer_note,
            "decided_by": row.decided_by,
            "decided_at": iso_utc(row.decided_at) if row.decided_at else None,
            "reason_codes": rules.review_reason_codes,
            "can_decide": row.status in WAITING
            and payment.state == PaymentState.PENDING_APPROVAL.value,
            "simulated": True,
            "disclaimer": DISCLAIMER,
        }

    @staticmethod
    def _hint(signals: list[dict[str, Any]]) -> dict[str, str]:
        """A fixed-rule hint, not a verdict: what a careful reviewer would usually do next."""
        codes = {s["code"] for s in signals}
        if "NO_INVOICE" in codes:
            nxt = ReviewDecision.ASK_INFO.value
            why = "No fee demand note is on file, so ask for it first."
        elif "NAME_CHECK" in codes:
            nxt = ReviewDecision.ASK_INFO.value
            why = "Ask the parent for the receiver's exact legal name from the invoice."
        else:
            nxt = ReviewDecision.CLEAR.value
            why = "The documents are on file; the signals are explained by routine reasons."
        return {"suggested": nxt, "why": why, "note": "A rule-based hint. The reviewer decides."}

    # --- acting ----------------------------------------------------------------------
    def decide(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        payment_id: str,
        *,
        decision: ReviewDecision,
        reason_code: str | None,
        note: str | None,
        mfa_proof_raw: str | None,
    ) -> dict[str, Any]:
        authorize(actor, Perm.REVIEW_DECIDE)
        payment = self._payments.load(session, actor, payment_id)
        row = self.review_of(session, payment.id)
        if row is None or row.status not in WAITING:
            raise errors.InvalidState("This payment has no review waiting for a decision.")
        if payment.state != PaymentState.PENDING_APPROVAL.value:
            raise errors.InvalidState("Only a payment that waits for approval can be reviewed.")
        text = _plain(note or "")
        if decision is not ReviewDecision.CLEAR:
            if reason_code not in rules.review_reason_codes:
                raise errors.ValidationFailed("Choose one of the listed reasons.")
            if len(text) < MIN_NOTE:
                raise errors.ValidationFailed("Write a short note the parent can read.")
        now = self._clock.now()
        proof = auth.find_valid_mfa_proof(
            session,
            raw=mfa_proof_raw,
            user_id=actor.user_id,
            scope="review_payment",
            subject_id=payment.id,
            now=now,
        )
        if proof is None:
            raise errors.MfaRequired(
                "Verify MFA again. The proof is missing, already used, or older than 5 minutes.",
                persist=True,
            )
        proof.used_at = now
        waited = int((now - row.opened_at).total_seconds() // 60)
        row.status = {
            ReviewDecision.CLEAR: ReviewStatus.CLEARED,
            ReviewDecision.ASK_INFO: ReviewStatus.INFO_REQUESTED,
            ReviewDecision.DECLINE: ReviewStatus.DECLINED,
        }[decision].value
        row.decided_at, row.decided_by, row.updated_at = now, actor.user_id, now
        row.reason_code = reason_code if decision is not ReviewDecision.CLEAR else "CLEARED"
        row.reviewer_note = text or None
        shown = {
            ReviewDecision.CLEAR: Decision.APPROVED,
            ReviewDecision.DECLINE: Decision.REJECTED,
            ReviewDecision.ASK_INFO: None,
        }[decision]
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank_review.decided",
            payment_id=payment.id,
            recipient_id=payment.recipient_id,
            decision=shown,
            reason_code=f"{decision.value}:{row.reason_code}"[:60],
            detail=f"{auth.proof_reference(proof)} waited_min={waited}",
        )
        if decision is ReviewDecision.DECLINE:
            self._payments.reject(session, actor, payment.id, f"Bank review: {row.reason_code}")
        session.flush()
        return self._reviewer_view(session, actor, rules, payment, row)

    def reply(
        self, session: Session, actor: Actor, rules: Rules, payment_id: str, message: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.REVIEW_ANSWER)
        payment = self._payments.load(session, actor, payment_id)
        row = self.review_of(session, payment.id)
        if row is None or row.status != ReviewStatus.INFO_REQUESTED.value:
            raise errors.InvalidState("The bank has not asked you anything on this payment.")
        text = _plain(message)
        if len(text) < MIN_NOTE:
            raise errors.ValidationFailed("Write a short answer for the bank.")
        now = self._clock.now()
        row.parent_reply = self._seal_reply(row, text)
        row.status = ReviewStatus.OPEN.value
        row.opened_at, row.due_at = now, now + timedelta(hours=rules.review_target_hours)
        row.updated_at = now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank_review.answered",
            payment_id=payment.id,
            recipient_id=payment.recipient_id,
            input_hash=hashlib.sha256(text.encode()).hexdigest(),
            detail=f"{len(text)} characters",
        )
        session.flush()
        return self._parent_view(rules, payment, row)

    def remind(
        self, session: Session, actor: Actor, rules: Rules, payment_id: str
    ) -> dict[str, Any]:
        authorize(actor, Perm.REVIEW_ANSWER)
        payment = self._payments.load(session, actor, payment_id)
        row = self.review_of(session, payment.id)
        now = self._clock.now()
        if row is None or not self._can_remind(row, rules, now):
            raise errors.InvalidState(
                "A reminder can be sent when the bank is reviewing and none was sent recently."
            )
        row.reminders += 1
        row.last_reminder_at, row.updated_at = now, now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank_review.reminded",
            payment_id=payment.id,
            recipient_id=payment.recipient_id,
            detail=f"reminder {row.reminders}, "
            + ("overdue" if now >= row.due_at else "before the target time"),
        )
        session.flush()
        return self._parent_view(rules, payment, row)

    # --- the reviewer's queue --------------------------------------------------------
    def queue(self, session: Session, actor: Actor, rules: Rules) -> dict[str, Any]:
        authorize(actor, Perm.REVIEW_DECIDE)
        now = self._clock.now()
        rows = list(
            session.execute(
                select(BankReview).where(BankReview.status.in_(WAITING)).limit(500)
            ).scalars()
        )
        rank = {"overdue": 0, "due_soon": 1, "on_time": 2, "not_running": 3}
        items: list[dict[str, Any]] = []
        for row in rows:
            payment = session.get(Payment, row.payment_id)
            quote = session.get(Quote, payment.quote_id) if payment else None
            if payment is None or quote is None:
                continue
            if payment.state != PaymentState.PENDING_APPROVAL.value:
                continue  # cancelled or moved on: nobody is waiting for it
            clock = self._clock_view(row, rules, now)
            codes = [s["code"] for s in self._signals(row)]
            people = sum(1 for s in self._signals(row) if s["needs_human"])
            items.append(
                {
                    "payment_id": payment.id,
                    "status": row.status,
                    "amount": Money(quote.target_amount_minor, quote.target_currency).to_dict(),
                    "purpose": quote.purpose,
                    "signals": [SIGNAL_TEXT[c]["title"] for c in codes],
                    "priority": row.priority_json,
                    "clock": clock,
                    "reminders": row.reminders,
                    "escalated": row.reminders > 0 and clock["state"] == "overdue",
                    "opened_at": iso_utc(row.opened_at),
                    "reasons_for_a_person": people,
                }
            )
        items.sort(
            # Urgency first (a late review is late whatever it is). Then the AI's risk reading when
            # it is loaded, or, without it, how many plain-rule reasons need a person.
            key=lambda i: (
                rank[i["clock"]["state"]],
                -(i["priority"]["percentile"] if i["priority"] else 0),
                -i["reasons_for_a_person"],
                i["opened_at"],
            )
        )
        decided = list(
            session.execute(
                select(BankReview.opened_at, BankReview.decided_at).where(
                    BankReview.decided_at.is_not(None)
                )
            ).all()
        )
        hours = [(d - o).total_seconds() / 3600.0 for o, d in decided]
        return {
            "items": items,
            "stats": {
                "waiting": len(items),
                "overdue": sum(1 for i in items if i["clock"]["state"] == "overdue"),
                "decided": len(hours),
                "average_hours_to_decide": round(sum(hours) / len(hours), 2) if hours else None,
                "target_hours": rules.review_target_hours,
            },
            "simulated": True,
            "disclaimer": DISCLAIMER,
        }
