"""Sandbox endpoints: what is simulated, and the reviewer's control of the simulated provider.

Both exist only while APP_ENV=sandbox; in production they answer 404 like any unknown path.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.context import AppContext
from app.api.deps import get_ctx, require
from app.api.schemas import ProviderEventIn
from app.core import errors
from app.domain.rbac import Actor, Perm
from app.domain.rules import load_rules
from app.domain.sandbox import describe_sandbox

router = APIRouter(tags=["sandbox"])


def sandbox_only(ctx: AppContext = Depends(get_ctx)) -> None:
    if not ctx.settings.is_sandbox:
        raise errors.NotFound("Not found.")


@router.get("/sandbox")
def sandbox_info(
    _: None = Depends(sandbox_only), ctx: AppContext = Depends(get_ctx)
) -> dict[str, Any]:
    """Public: what is simulated, the test scenarios, timings and the demo accounts."""
    with ctx.db.read() as session:
        rules = load_rules(session)
    mode = str(getattr(ctx.assistant, "mode", "unavailable"))
    return describe_sandbox(ctx.settings, rules, mode)


@router.post("/sandbox/payments/{payment_id}/provider-event")
def provider_event(
    payment_id: str,
    body: ProviderEventIn,
    _: None = Depends(sandbox_only),
    actor: Actor = Depends(require(Perm.SANDBOX_CONTROL)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Reviewer only: bring the simulated provider's settle or fail webhook forward."""
    with ctx.db.write() as session:
        return ctx.sandbox.schedule_provider_event(session, actor, payment_id, body.outcome)
