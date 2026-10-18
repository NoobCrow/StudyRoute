"""Programmable escrow and the audit anchor on the SANDBOX chain.

Exists only while APP_ENV=sandbox; in production every path answers 404 like an unknown path.
Planning is free, but locking funds, paying a tranche early and cancelling each need a fresh MFA
proof for that exact escrow, and the writes need an Idempotency-Key. The AI has no permission
here. Nothing is real: the chain is an in-memory simulation and the tokens are not money.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.api.deps import get_ctx, idempotency_key, limit_user, require
from app.api.idempotency import run_idempotent
from app.api.schemas import ChainAdvanceIn, EscrowPlanIn, ReasonIn
from app.core import errors
from app.domain.rbac import Actor, Perm
from app.domain.rules import Rules

router = APIRouter(tags=["escrow"])


def sandbox_only(ctx: AppContext = Depends(get_ctx)) -> None:
    if not ctx.settings.is_sandbox:
        raise errors.NotFound("Not found.")


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


# --- escrows ---------------------------------------------------------------------------------
@router.get("/escrows")
def list_escrows(
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        rows = ctx.escrow.list(session, actor)
        items = [ctx.escrow.view(session, actor, r, detail=True) for r in rows]
        return {"items": items, "simulated": True}


@router.get("/escrows/{escrow_id}")
def get_escrow(
    escrow_id: str,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        row = ctx.escrow.get(session, actor, escrow_id)
        return ctx.escrow.view(session, actor, row, detail=True)


@router.post("/escrows", status_code=201)
def plan_escrow(
    body: EscrowPlanIn,
    request: Request,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_WRITE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Work out the schedule. Nothing is locked until a human confirms with MFA."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        row = ctx.escrow.plan(
            session,
            actor,
            rules,
            recipient_id=body.recipient_id,
            purpose=body.purpose,
            total_minor=body.total.amount_minor,
            currency=body.total.currency,
            tranches=body.tranches,
            first_release=body.first_release,
            cadence=body.cadence,
            reference=body.reference,
        )
        return 201, ctx.escrow.view(session, actor, row, detail=True)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/escrows/{escrow_id}/confirm")
def confirm_escrow(
    escrow_id: str,
    request: Request,
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_WRITE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Human only: lock the funds in the escrow contract. Needs MFA for this exact escrow."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        row = ctx.escrow.confirm(session, actor, rules, escrow_id, x_mfa_proof)
        return 200, ctx.escrow.view(session, actor, row, detail=True)

    return _idempotent(ctx, request, actor, key, {"escrow_id": escrow_id}, work)


@router.post("/escrows/{escrow_id}/abandon")
def abandon_escrow(
    escrow_id: str,
    request: Request,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_WRITE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        row = ctx.escrow.abandon(session, actor, escrow_id)
        return 200, ctx.escrow.view(session, actor, row, detail=True)

    return _idempotent(ctx, request, actor, key, {"escrow_id": escrow_id}, work)


@router.post("/escrows/{escrow_id}/tranches/{index}/release")
def release_tranche(
    escrow_id: str,
    index: int,
    request: Request,
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_WRITE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Human only: pay one tranche before its date. Needs MFA for this exact escrow."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        row = ctx.escrow.release_early(session, actor, escrow_id, index, x_mfa_proof)
        return 200, ctx.escrow.view(session, actor, row, detail=True)

    return _idempotent(ctx, request, actor, key, {"escrow_id": escrow_id, "index": index}, work)


@router.post("/escrows/{escrow_id}/cancel")
def cancel_escrow(
    escrow_id: str,
    request: Request,
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_WRITE)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Human only: take back every tranche that is not yet due. Needs MFA."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        row = ctx.escrow.cancel(session, actor, escrow_id, x_mfa_proof)
        return 200, ctx.escrow.view(session, actor, row, detail=True)

    return _idempotent(ctx, request, actor, key, {"escrow_id": escrow_id}, work)


@router.post("/escrows/{escrow_id}/freeze")
def freeze_escrow(
    escrow_id: str,
    body: ReasonIn,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_FREEZE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: stop all movement. The funds stay locked; a freeze cannot move them."""
    with ctx.db.write() as session:
        row = ctx.escrow.freeze(session, actor, escrow_id, body.reason)
        return ctx.escrow.view(session, actor, row, detail=True)


@router.post("/escrows/{escrow_id}/unfreeze")
def unfreeze_escrow(
    escrow_id: str,
    body: ReasonIn,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.ESCROW_FREEZE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.write() as session:
        row = ctx.escrow.unfreeze(session, actor, escrow_id, body.reason)
        return ctx.escrow.view(session, actor, row, detail=True)


@router.post("/escrows/{escrow_id}/tranches/{index}/sandbox-refund")
def sandbox_refund(
    escrow_id: str,
    index: int,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.SANDBOX_CONTROL)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: play the university sending a tranche back (a refused visa, say)."""
    with ctx.db.write() as session:
        row = ctx.escrow.university_refund(session, actor, escrow_id, index)
        return ctx.escrow.view(session, actor, row, detail=True)


# --- the chain ----------------------------------------------------------------------------------
@router.get("/chain/status")
def chain_status(
    _: None = Depends(sandbox_only),
    __: Actor = Depends(require(Perm.CHAIN_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """The contracts, their addresses, the newest block and whether the log is intact."""
    with ctx.db.read() as session:
        return ctx.chain.status(session)


@router.get("/chain/anchors")
def chain_anchors(
    _: None = Depends(sandbox_only),
    __: Actor = Depends(require(Perm.CHAIN_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {"items": ctx.chain.anchors(session), "simulated": True}


@router.post("/chain/anchor", status_code=201)
def anchor_audit(
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.CHAIN_ANCHOR)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: write the audit log's newest hash onto the chain, outside the database."""
    with ctx.db.write() as session:
        return {**ctx.chain.anchor_audit(session, actor.user_id), "simulated": True}


@router.get("/chain/verify")
def verify_anchors(
    _: None = Depends(sandbox_only),
    __: Actor = Depends(require(Perm.AUDIT_VERIFY)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: does the database still match every hash anchored on the chain?"""
    with ctx.db.read() as session:
        return ctx.chain.verify_anchors(session)


@router.post("/chain/sandbox/advance")
def advance_time(
    body: ChainAdvanceIn,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.SANDBOX_CONTROL)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: move chain time forward as if days had passed, then pay what is now due."""
    with ctx.db.write() as session:
        ctx.chain.advance(session, seconds=body.days * 86_400, actor_id=actor.user_id)
        ctx.audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="chain.time_advanced",
            detail=f"Sandbox chain time moved forward {body.days} day(s)",
        )
    released = ctx.escrow.advance_due(ctx.db)
    with ctx.db.read() as session:
        return {"released": released, "status": ctx.chain.status(session)}
