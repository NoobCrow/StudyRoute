"""The "Reset my data" button: delete a household's business data, keep the audit chain."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.domain.rbac import Actor, Perm, authorize
from app.models import (
    Document,
    IdempotencyKey,
    MfaProof,
    Payment,
    PaymentTransition,
    ProviderLedger,
    Quote,
    Recipient,
)


def reset_household_data(session: Session, audit: AuditService, actor: Actor) -> dict[str, int]:
    """Remove payments, quotes, recipients and documents. Audit events stay (no personal data)."""
    authorize(actor, Perm.DATA_RESET)
    owner = actor.owner_id or actor.user_id
    ids = list(session.execute(select(Payment.id).where(Payment.owner_id == owner)).scalars())
    if ids:
        session.execute(delete(Document).where(Document.payment_id.in_(ids)))
        session.execute(delete(ProviderLedger).where(ProviderLedger.payment_id.in_(ids)))
        session.execute(delete(PaymentTransition).where(PaymentTransition.payment_id.in_(ids)))
    counts: dict[str, int] = {}
    for name, table in (
        ("documents", Document),
        ("payments", Payment),
        ("quotes", Quote),
        ("recipients", Recipient),
    ):
        counts[name] = session.execute(delete(table).where(table.owner_id == owner)).rowcount
    session.execute(delete(IdempotencyKey).where(IdempotencyKey.user_id == actor.user_id))
    session.execute(delete(MfaProof).where(MfaProof.user_id == actor.user_id))
    detail = ", ".join(f"{name}={count}" for name, count in counts.items())
    audit.append(
        session,
        actor_type=actor.audit_type,
        actor_id=actor.user_id,
        action="user.data_reset",
        detail=detail,
    )
    return counts
