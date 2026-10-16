"""Authenticated assistant chat and request-scoped cloud connection checks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.ai.cloud import CloudError, byok_client, default_cloud
from app.ai.guards import GuardFailure, parse_llm_json
from app.api.context import AppContext
from app.api.deps import get_ctx, limit_user, require
from app.api.schemas import ChatIn, CloudConnectionIn
from app.core import errors
from app.domain.rbac import Actor, Perm

router = APIRouter(tags=["assistant"])


@router.post("/assistant/connection/test")
def check_connection(
    body: CloudConnectionIn,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("chat")),
) -> dict[str, Any]:
    """Test with a synthetic ping only. Never store, echo, audit or log credentials."""
    llm = byok_client(ctx.settings, body.provider, body.api_key.get_secret_value())
    try:
        result = llm.complete(
            system='Return exactly {"reply":"Connected","facts_used":[],"proposed_actions":[]}.',
            user="Connection check. No customer data is included.",
        )
        parsed = parse_llm_json(result.text)
        if not isinstance(parsed.get("reply"), str) or not parsed["reply"].strip():
            raise CloudError(body.provider, "bad_response")
    except (CloudError, GuardFailure) as exc:
        problem = exc if isinstance(exc, CloudError) else CloudError(body.provider, "bad_response")
        return {"ok": False, "availability": problem.to_api()}
    return {"ok": True, "provider": body.provider, "model": llm.model}


@router.post("/assistant/chat")
def chat(
    body: ChatIn,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("chat")),
) -> dict[str, Any]:
    if ctx.assistant is None:
        raise errors.Internal("The assistant is not available.")
    assistant = ctx.assistant
    if body.connection is not None:
        assistant = assistant.with_llm(
            byok_client(
                ctx.settings, body.connection.provider, body.connection.api_key.get_secret_value()
            )
        )
    elif ctx.settings.assistant_cloud_enabled and assistant.mode != "llm":
        assistant = assistant.with_llm(default_cloud(ctx.settings))
    return assistant.chat(
        actor,
        body.message,
        quote_id=body.context.quote_id,
        payment_id=body.context.payment_id,
        pending=body.context.pending,
        history=body.context.history,
        conversation=[(turn.role, turn.text) for turn in body.context.conversation],
    )
