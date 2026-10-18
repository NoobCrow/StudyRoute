"""The sandbox bank's review desk: queue, one page per payment, and the three answers.

A reviewer (an admin user, a human) reads the queue and answers with a fresh MFA proof. A parent
reads the plain-language page, answers a question from the bank, or sends a reminder. The AI can
read the parent's page to explain it and can do nothing else here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.api.deps import get_ctx, idempotency_key, limit_user, require
from app.api.idempotency import run_idempotent
from app.api.schemas import ReviewDecisionIn, ReviewReplyIn
from app.domain.constants import ReviewDecision
from app.domain.rbac import Actor, Perm
from app.domain.rules import Rules, load_rules

router = APIRouter(tags=["bank-review"])


def _idempotent(
    ctx: AppContext, request: Request, actor: Actor, key: str, body: dict[str, Any], work: Any
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


@router.get("/bank-review/queue")
def review_queue(
    actor: Actor = Depends(require(Perm.REVIEW_DECIDE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Payments waiting for a bank reviewer: most overdue first, then the model's priority."""
    with ctx.db.read() as session:
        return ctx.reviews.queue(session, actor, load_rules(session))


@router.get("/payments/{payment_id}/bank-review")
def get_review(
    payment_id: str,
    actor: Actor = Depends(require(Perm.REVIEW_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """The reviewer's one page (admin) or the parent's plain-language page (everyone else)."""
    with ctx.db.read() as session:
        return ctx.reviews.view(session, actor, load_rules(session), payment_id)


@router.post("/payments/{payment_id}/bank-review/decision")
def decide_review(
    payment_id: str,
    body: ReviewDecisionIn,
    request: Request,
    actor: Actor = Depends(require(Perm.REVIEW_DECIDE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    """Yes, no or ask for more. A human only, with a fresh MFA proof for this payment."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        result = ctx.reviews.decide(
            session,
            actor,
            rules,
            payment_id,
            decision=ReviewDecision(body.decision),
            reason_code=body.reason_code,
            note=body.note,
            mfa_proof_raw=x_mfa_proof,
        )
        return 200, result

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/payments/{payment_id}/bank-review/reply")
def reply_review(
    payment_id: str,
    body: ReviewReplyIn,
    request: Request,
    actor: Actor = Depends(require(Perm.REVIEW_ANSWER)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    """The parent's short answer to the bank's question. The review goes back to the queue."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        return 200, ctx.reviews.reply(session, actor, rules, payment_id, body.message)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/payments/{payment_id}/bank-review/remind")
def remind_review(
    payment_id: str,
    request: Request,
    actor: Actor = Depends(require(Perm.REVIEW_ANSWER)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("payment_writes")),
) -> JSONResponse:
    """A reminder to the bank's queue (not more than one in a few hours)."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        return 200, ctx.reviews.remind(session, actor, rules, payment_id)

    return _idempotent(ctx, request, actor, key, {}, work)
