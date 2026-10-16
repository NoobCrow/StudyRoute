"""Authenticated assistant chat and request-scoped cloud connection checks."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from app.ai.cloud import CloudError, byok_client, default_cloud
from app.ai.guards import GuardFailure, parse_llm_json
from app.api.context import AppContext
from app.api.deps import get_ctx, limit_user, require
from app.api.schemas import ChatIn, CloudConnectionIn, SaveCloudConnectionIn
from app.core import errors
from app.core.clock import iso_utc
from app.core.crypto import DecryptionError
from app.domain.constants import ActorKind
from app.domain.rbac import Actor, Perm
from app.models import SavedAIConnection

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


def _human(actor: Actor) -> None:
    if actor.kind not in {ActorKind.PARENT, ActorKind.STUDENT, ActorKind.ADMIN}:
        raise errors.Forbidden("Only the signed-in person can manage saved API keys.")


def _metadata(row: SavedAIConnection | None) -> dict[str, Any]:
    if row is None:
        return {"saved": False}
    return {
        "saved": True,
        "provider": row.provider,
        "model": row.model,
        "verified": row.verified,
        "updated_at": iso_utc(row.updated_at),
    }


def _key_context(user_id: str, provider: str) -> str:
    return f"saved-ai-key:{user_id}:{provider}"


@router.get("/assistant/connection")
def saved_connection(
    response: Response,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    """Metadata only: never return the plaintext key, ciphertext or key suffix."""
    _human(actor)
    response.headers["Cache-Control"] = "no-store"
    with ctx.db.read() as session:
        return _metadata(session.get(SavedAIConnection, actor.user_id))


@router.put("/assistant/connection")
def save_connection(
    body: SaveCloudConnectionIn,
    response: Response,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_user("chat")),
) -> dict[str, Any]:
    """Explicit storage consent, synthetic test, then atomic encrypted replacement."""
    _human(actor)
    response.headers["Cache-Control"] = "no-store"
    tested = check_connection(body, actor, ctx)
    availability = tested.get("availability")
    # Quota exhaustion is not a successful validation. Still allow saving with an
    # honest unverified label, so the user need not re-enter it after the limit resets.
    if not tested["ok"] and (not availability or availability["code"] != "quota_exhausted"):
        return {**tested, "saved": False}
    llm = byok_client(ctx.settings, body.provider, body.api_key.get_secret_value())
    sealed = ctx.cipher.encrypt(
        body.api_key.get_secret_value(), context=_key_context(actor.user_id, body.provider)
    )
    with ctx.db.write() as session:
        row = session.get(SavedAIConnection, actor.user_id)
        if row is None:
            row = SavedAIConnection(user_id=actor.user_id)
            session.add(row)
        row.provider, row.model, row.api_key_enc = body.provider, llm.model, sealed
        row.verified, row.updated_at = bool(tested["ok"]), ctx.clock.now()
        session.flush()
        result = _metadata(row)
    return {**result, "ok": True, **({"availability": availability} if availability else {})}


@router.delete("/assistant/connection")
def delete_connection(
    response: Response,
    actor: Actor = Depends(require(Perm.CHAT_USE)),
    ctx: AppContext = Depends(get_ctx),
) -> dict[str, Any]:
    _human(actor)
    response.headers["Cache-Control"] = "no-store"
    with ctx.db.write() as session:
        row = session.get(SavedAIConnection, actor.user_id)
        if row is not None:
            session.delete(row)
    return {"saved": False, "removed": True}


def _saved_client(actor: Actor, ctx: AppContext):
    # Delegated AI/household visibility never grants access to a person's saved key.
    if actor.kind not in {ActorKind.PARENT, ActorKind.STUDENT, ActorKind.ADMIN}:
        return None
    with ctx.db.read() as session:
        row = session.get(SavedAIConnection, actor.user_id)
        if row is None:
            return None
        try:
            key = ctx.cipher.decrypt(
                row.api_key_enc, context=_key_context(actor.user_id, row.provider)
            )
        except DecryptionError:
            raise errors.InvalidState(
                "The saved API key cannot be decrypted. Remove and save it again, or restore "
                "the original DATA_ENCRYPTION_KEY/server dev secrets. No default provider was used."
            ) from None
        return byok_client(ctx.settings, row.provider, key)


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
    else:
        saved = _saved_client(actor, ctx)
        if saved is not None:
            assistant = assistant.with_llm(saved)
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
