"""AI explainer chat. The assistant explains engine numbers; it never acts on its own."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.api.context import AppContext
from app.api.deps import get_ctx, limit_user, require
from app.api.schemas import ChatIn
from app.core import errors
from app.domain.rbac import Actor, Perm

router = APIRouter(tags=["assistant"])


@router.post("/assistant/chat")
def chat(
    body: ChatIn,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("chat")),
) -> dict[str, Any]:
    if ctx.assistant is None:
        raise errors.Internal("The assistant is not available.")
    result: dict[str, Any] = ctx.assistant.chat(
        actor,
        body.message,
        quote_id=body.context.quote_id,
        payment_id=body.context.payment_id,
        pending=body.context.pending,
        history=body.context.history,
    )
    return result
