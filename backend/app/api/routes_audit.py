"""Audit log endpoints: list events and verify the hash chain."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select

from app.api.context import AppContext
from app.api.deps import get_ctx, require
from app.audit.service import event_dict
from app.domain.constants import ActorKind
from app.domain.rbac import Actor, Perm
from app.engine.money import Money
from app.models import AuditEvent, Payment, Quote, Recipient

router = APIRouter(tags=["audit"])


def _view(row: AuditEvent) -> dict[str, Any]:
    body = event_dict(row)
    if row.amount_minor is not None and row.currency:
        body["amount_display"] = Money(row.amount_minor, row.currency).format()
    return body


@router.get("/audit/events")
def list_events(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    payment_id: str | None = Query(default=None, max_length=64),
    action: str | None = Query(default=None, max_length=48),
    actor: Actor = Depends(require(Perm.AUDIT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    stmt = select(AuditEvent).order_by(AuditEvent.seq.desc())
    if actor.kind is not ActorKind.ADMIN:
        owner = actor.owner_id or actor.user_id
        stmt = stmt.where(
            or_(
                AuditEvent.actor_id == actor.user_id,
                AuditEvent.payment_id.in_(select(Payment.id).where(Payment.owner_id == owner)),
                AuditEvent.quote_id.in_(select(Quote.id).where(Quote.owner_id == owner)),
                AuditEvent.recipient_id.in_(
                    select(Recipient.id).where(Recipient.owner_id == owner)
                ),
            )
        )
    if payment_id:
        stmt = stmt.where(AuditEvent.payment_id == payment_id)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if cursor:
        stmt = stmt.where(AuditEvent.seq < cursor)
    with ctx.db.read() as session:
        rows = list(session.execute(stmt.limit(limit + 1)).scalars())
        page = rows[:limit]
        items = [_view(r) for r in page]
        next_cursor = page[-1].seq if len(rows) > limit and page else None
    return {
        "items": items,
        "next_cursor": next_cursor,
        "scope": "all events" if actor.kind is ActorKind.ADMIN else "your events",
    }


@router.get("/audit/verify")
def verify_chain(
    expected_head: str | None = Query(default=None, min_length=64, max_length=64),
    actor: Actor = Depends(require(Perm.AUDIT_VERIFY)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        result = ctx.audit.verify(session, expected_head=expected_head)
    return result.to_api_dict()
