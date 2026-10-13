"""Mock KYC gate (blueprint 11.2). Synthetic only: no real identity data is ever stored.

NEEDS_DOCUMENTS -> (submit all required documents) -> PENDING -> (simulated review) -> VERIFIED
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.ids import new_id
from app.domain.constants import ActorType, Decision, KycStatus
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import Rules
from app.models import KycRecord, User

_KIND = re.compile(r"[a-z0-9_]{2,40}")

MESSAGES = {
    KycStatus.VERIFIED: "KYC verified (simulated). Approval is available.",
    KycStatus.PENDING: "Your documents are being reviewed (simulated).",
    KycStatus.NEEDS_DOCUMENTS: "Documents are missing. Approval is blocked until they are added.",
}


class KycService:
    def __init__(self, clock: Clock, audit: AuditService) -> None:
        self._clock = clock
        self._audit = audit

    def _payer(self, session: Session, actor: Actor) -> User:
        if actor.owner_id is None:
            raise errors.Forbidden("KYC belongs to the paying parent.")
        payer = session.get(User, actor.owner_id)
        if payer is None:
            raise errors.NotFound("Payer not found.")
        return payer

    def _latest(self, session: Session, user_id: str) -> KycRecord | None:
        return session.execute(
            select(KycRecord)
            .where(KycRecord.user_id == user_id)
            .order_by(KycRecord.submitted_at.desc().nulls_last(), KycRecord.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _set_status(
        self, session: Session, user: User, new: KycStatus, actor_type: Any, actor_id: str, why: str
    ) -> None:
        old = user.kyc_status
        user.kyc_status = new.value
        self._audit.append(
            session,
            actor_type=actor_type,
            actor_id=actor_id,
            action="kyc.status_changed",
            decision=Decision.APPROVED if new is KycStatus.VERIFIED else None,
            reason_code=why,
            detail=f"{old}>{new.value} for {user.id}",
        )

    def view(self, session: Session, actor: Actor, rules: Rules) -> dict[str, Any]:
        authorize(actor, Perm.KYC_READ)
        payer = self._payer(session, actor)
        return self._view(session, payer, rules)

    def _view(self, session: Session, payer: User, rules: Rules) -> dict[str, Any]:
        record = self._latest(session, payer.id)
        status = KycStatus(payer.kyc_status)
        labels = rules.raw("checklist_labels")
        required = rules.kyc_required_documents
        provided = [d["kind"] for d in (record.mock_doc_refs if record else [])]
        missing = [k for k in required if k not in provided]
        return {
            "user_id": payer.id,
            "status": status.value,
            "message": MESSAGES[status],
            "simulated": True,
            "required_documents": [
                {"key": k, "label": labels.get(k, {}).get("label", k)} for k in required
            ],
            "provided_documents": provided,
            "missing": missing if status is not KycStatus.VERIFIED else [],
            "submitted_at": iso_utc(record.submitted_at)
            if record and record.submitted_at
            else None,
            "review_due_at": iso_utc(record.review_due_at)
            if record and record.review_due_at
            else None,
        }

    def mock_submit(
        self, session: Session, actor: Actor, rules: Rules, documents: list[str]
    ) -> dict[str, Any]:
        authorize(actor, Perm.KYC_SUBMIT)
        payer = self._payer(session, actor)
        kinds = sorted({d.strip().lower() for d in documents})
        if not kinds or not all(_KIND.fullmatch(k) for k in kinds):
            raise errors.ValidationFailed("Give document kinds such as passport or parent_id.")
        if payer.kyc_status == KycStatus.VERIFIED.value:
            return self._view(session, payer, rules)
        now = self._clock.now()
        missing = [k for k in rules.kyc_required_documents if k not in kinds]
        status = KycStatus.NEEDS_DOCUMENTS if missing else KycStatus.PENDING
        session.add(
            KycRecord(
                id=new_id("kyc"),
                user_id=payer.id,
                status=status.value,
                mock_doc_refs=[
                    {
                        "kind": k,
                        "ref": "mock-" + hashlib.sha256(f"{payer.id}:{k}".encode()).hexdigest()[:8],
                    }
                    for k in kinds
                ],
                missing=missing,
                submitted_by=actor.user_id,
                submitted_at=now,
                review_due_at=None
                if missing
                else now + timedelta(seconds=rules.kyc_review_seconds),
            )
        )
        session.flush()
        self._set_status(session, payer, status, actor.audit_type, actor.user_id, "MOCK_SUBMIT")
        return self._view(session, payer, rules)

    def mock_review(
        self, session: Session, actor: Actor, rules: Rules, user_id: str, status: KycStatus
    ) -> dict[str, Any]:
        authorize(actor, Perm.KYC_REVIEW)
        payer = session.get(User, user_id)
        if payer is None or payer.role != "parent":
            raise errors.NotFound("Payer not found.")
        now = self._clock.now()
        record = self._latest(session, payer.id)
        if record is not None:
            record.status = status.value
            record.reviewed_at = now
        self._set_status(session, payer, status, actor.audit_type, actor.user_id, "ADMIN_REVIEW")
        return self._view(session, payer, rules)

    def complete_due_reviews(self, session: Session) -> int:
        """Finish simulated reviews whose time has come (called by the worker and before guards)."""
        now = self._clock.now()
        due = (
            session.execute(
                select(KycRecord).where(
                    KycRecord.status == KycStatus.PENDING.value,
                    KycRecord.review_due_at.is_not(None),
                    KycRecord.review_due_at <= now,
                )
            )
            .scalars()
            .all()
        )
        done = 0
        for record in due:
            user = session.get(User, record.user_id)
            record.status = KycStatus.VERIFIED.value
            record.reviewed_at = now
            if user is not None and user.kyc_status == KycStatus.PENDING.value:
                self._set_status(
                    session,
                    user,
                    KycStatus.VERIFIED,
                    ActorType.SYSTEM,
                    "system",
                    "SIMULATED_REVIEW",
                )
                done += 1
        return done
