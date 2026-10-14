"""Payment endpoints (blueprint 8.2 and 8.3). Writes are idempotent."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.api.deps import current_actor, get_ctx, idempotency_key, limit_user, require
from app.api.idempotency import run_idempotent
from app.api.schemas import ApproveIn, PaymentIn, RejectIn, RequoteIn
from app.domain.rbac import Actor, Perm
from app.domain.rules import Rules, load_rules

router = APIRouter(tags=["payments"])


def _idempotent(
    ctx: AppContext,
    request: Request,
    actor: Actor,
    key: str,
    body: dict[str, Any],
    work: Any,
) -> JSONResponse:
    return run_idempotent(
        ctx,
        actor=actor,
        key=key,
        method=request.method,
        path=request.url.path,
        body=body,
        work=work,
    )


@router.post("/payments", status_code=201)
def create_payment(
    body: PaymentIn,
    request: Request,
    actor: Actor = Depends(require(Perm.PAYMENT_CREATE_DRAFT)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        payment = ctx.payments.create(
            session,
            actor,
            rules,
            quote_id=body.quote_id,
            provider_id=body.provider_id,
            recipient_id=body.recipient_id,
            reference=body.reference,
            due_date=body.due_date,
        )
        return 201, ctx.payments.view(session, rules, payment)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.get("/payments")
def list_payments(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=120),
    actor: Actor = Depends(require(Perm.PAYMENT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rows, next_cursor = ctx.payments.list(session, actor, limit, cursor)
        return {"items": [ctx.payments.brief(session, r) for r in rows], "next_cursor": next_cursor}


@router.get("/payments/{payment_id}")
def get_payment(
    payment_id: str,
    actor: Actor = Depends(require(Perm.PAYMENT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        payment = ctx.payments.load(session, actor, payment_id)
        return ctx.payments.view(session, load_rules(session), payment)


@router.get("/payments/{payment_id}/tracker")
def payment_tracker(
    payment_id: str,
    actor: Actor = Depends(require(Perm.PAYMENT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.payments.tracker(session, actor, load_rules(session), payment_id)


@router.get("/payments/{payment_id}/instruction-preview")
def instruction_preview(
    payment_id: str,
    actor: Actor = Depends(require(Perm.PAYMENT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.payments.instruction_preview(session, actor, payment_id)


@router.get("/payments/{payment_id}/compliance-report")
def compliance_report(
    payment_id: str,
    actor: Actor = Depends(require(Perm.AUDIT_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """An evidence pack for one payment: parties, controls, approval proof, audit excerpt."""
    with ctx.db.read() as session:
        return ctx.reports.payment_report(session, actor, load_rules(session), payment_id)


@router.post("/payments/{payment_id}/request-approval")
def request_approval(
    payment_id: str,
    request: Request,
    actor: Actor = Depends(require(Perm.PAYMENT_REQUEST_APPROVAL)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        return 200, ctx.payments.request_approval(session, actor, rules, payment_id)

    return _idempotent(ctx, request, actor, key, {}, work)


@router.post("/payments/{payment_id}/approve")
def approve_payment(
    payment_id: str,
    body: ApproveIn,
    request: Request,
    actor: Actor = Depends(current_actor),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    """Human approval. The AI token is refused inside the service with AI_CANNOT_APPROVE."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        result = ctx.payments.approve(
            session,
            actor,
            rules,
            payment_id,
            confirm_hash=body.confirm_summary_hash,
            mfa_proof_raw=x_mfa_proof,
        )
        return 200, result

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/payments/{payment_id}/reject")
def reject_payment(
    payment_id: str,
    body: RejectIn,
    request: Request,
    actor: Actor = Depends(require(Perm.PAYMENT_REJECT)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        payment = ctx.payments.reject(session, actor, payment_id, body.reason)
        return 200, ctx.payments.view(session, rules, payment)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/payments/{payment_id}/cancel")
def cancel_payment(
    payment_id: str,
    request: Request,
    actor: Actor = Depends(require(Perm.PAYMENT_CANCEL)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        payment = ctx.payments.cancel(session, actor, payment_id)
        return 200, ctx.payments.view(session, rules, payment)

    return _idempotent(ctx, request, actor, key, {}, work)


@router.post("/payments/{payment_id}/requote")
def requote_payment(
    payment_id: str,
    body: RequoteIn,
    request: Request,
    actor: Actor = Depends(require(Perm.PAYMENT_CREATE_DRAFT)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        payment = ctx.payments.requote(
            session, actor, payment_id, quote_id=body.quote_id, provider_id=body.provider_id
        )
        return 200, ctx.payments.view(session, rules, payment)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)
