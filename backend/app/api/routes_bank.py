"""Sandbox bank network endpoints: accounts, transfers, the ledger overview and reviewer control.

Exists only while APP_ENV=sandbox; in production every path answers 404 like an unknown path.
Creating and confirming a transfer are payment-creating writes, so both need an Idempotency-Key;
confirming also needs a fresh MFA proof for that exact transfer. The AI has no bank permission.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.api.deps import get_ctx, idempotency_key, limit_user, require
from app.api.idempotency import run_idempotent
from app.api.schemas import BankStepIn, BankTransferIn
from app.core import errors
from app.domain.rbac import Actor, Perm
from app.domain.rules import Rules, load_rules
from app.engine.money import Money

router = APIRouter(prefix="/bank", tags=["bank"])


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


@router.get("/network")
def network(
    _: None = Depends(sandbox_only),
    __: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """The invented banks and rails, the ledger totals and whether every mirror account agrees."""
    with ctx.db.read() as session:
        ready = ctx.bank.is_ready(session)
        overview = ctx.bank.network_overview(session) if ready else {}
    return {"ready": ready, **overview, "simulated": True}


@router.get("/accounts")
def accounts(
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {
            "items": ctx.bank.list_accounts(session, actor),
            "totals": ctx.bank.household_totals(session, actor, load_rules(session)),
            "simulated": True,
        }


@router.get("/beneficiaries")
def beneficiaries(
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {"items": ctx.bank.list_beneficiaries(session, actor), "simulated": True}


@router.get("/accounts/{account_id}/statement")
def statement(
    account_id: str,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.bank.statement(session, actor, account_id)


@router.get("/transfers")
def list_transfers(
    limit: int = Query(default=20, ge=1, le=100),
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return {"items": ctx.bank.list_transfers(session, actor, limit), "simulated": True}


@router.get("/transfers/{transfer_id}")
def get_transfer(
    transfer_id: str,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_READ)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    with ctx.db.read() as session:
        return ctx.bank.get_transfer(session, actor, transfer_id)


@router.post("/transfers", status_code=201)
def create_transfer(
    body: BankTransferIn,
    request: Request,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_TRANSFER)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Plan a transfer. Nothing moves until a human confirms it with MFA."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        transfer = ctx.bank.create_transfer(
            session,
            actor,
            rules,
            source=body.source,
            destination=body.destination,
            amount=Money(body.amount.amount_minor, body.amount.currency),
            rail=body.rail,
            charge_code=body.charge_code,
            reference=body.reference,
        )
        return 201, ctx.bank.transfer_view(session, transfer, detail=True)

    return _idempotent(ctx, request, actor, key, body.model_dump(mode="json"), work)


@router.post("/transfers/{transfer_id}/confirm")
def confirm_transfer(
    transfer_id: str,
    request: Request,
    x_mfa_proof: str | None = Header(default=None),
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_TRANSFER)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
    __: None = Depends(limit_user("bank_writes")),
) -> JSONResponse:
    """Human only: reserve the funds and start it. Needs an MFA proof for this exact transfer."""

    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        transfer = ctx.bank.confirm(session, actor, transfer_id, x_mfa_proof)
        return 200, ctx.bank.transfer_view(session, transfer, detail=True)

    return _idempotent(ctx, request, actor, key, {"transfer_id": transfer_id}, work)


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(
    transfer_id: str,
    request: Request,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.BANK_TRANSFER)),
    key: str = Depends(idempotency_key),
    ctx: AppContext = Depends(get_ctx),
) -> JSONResponse:
    def work(session: Session, rules: Rules) -> tuple[int, dict[str, Any]]:
        transfer = ctx.bank.cancel(session, actor, transfer_id)
        return 200, ctx.bank.transfer_view(session, transfer, detail=True)

    return _idempotent(ctx, request, actor, key, {"transfer_id": transfer_id}, work)


@router.post("/transfers/{transfer_id}/sandbox-step")
def sandbox_step(
    transfer_id: str,
    body: BankStepIn,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.SANDBOX_CONTROL)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: run the next hop now, or make the transfer fail to show the full return."""
    with ctx.db.write() as session:
        transfer = ctx.bank.sandbox_control(session, actor, transfer_id, body.outcome)
        return ctx.bank.transfer_view(session, transfer, detail=True)
