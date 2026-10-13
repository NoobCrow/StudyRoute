"""Inbound signed provider webhooks (blueprint 8.5). Raw body first, then everything else."""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app.api.context import AppContext
from app.api.deps import client_ip, get_ctx
from app.core import errors
from app.core.crypto import sha256_ref
from app.domain.constants import ActorType, Decision
from app.domain.rules import load_rules
from app.engine.validators import is_valid_uetr
from app.models import WebhookEvent
from app.providers import webhooks

router = APIRouter(tags=["webhooks"])
_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]{6,80}$")
_EVENTS = {"payment.settled", "payment.failed"}


def _reject(ctx: AppContext, raw: bytes, ip: str, code: str, message: str) -> errors.ApiError:
    ctx.limiter.check("webhook_failures", ip)
    with ctx.db.write() as session:
        ctx.audit.append(
            session,
            actor_type=ActorType.PROVIDER,
            actor_id="unverified",
            action="webhook.rejected",
            decision=Decision.BLOCKED,
            reason_code=code,
            input_hash=sha256_ref(raw),
        )
    return errors.Unauthenticated(message)


def _handle(
    ctx: AppContext, raw: bytes, signature: str | None, event_id: str | None, ip: str
) -> JSONResponse:
    with ctx.db.read() as session:
        provider_ids = load_rules(session).provider_ids()
    secrets_by_provider = {pid: ctx.secrets.webhook_secrets(pid) for pid in provider_ids}
    try:
        provider_id = webhooks.verify(signature, raw, secrets_by_provider, ctx.clock.now())
    except webhooks.WebhookRejected as rejected:
        raise _reject(ctx, raw, ip, rejected.reason_code, rejected.message) from None
    ctx.limiter.check("webhooks", provider_id)
    if not event_id or not _EVENT_ID.match(event_id):
        raise errors.BadRequest("The X-Event-Id header is missing or malformed.")

    now = ctx.clock.now()
    with ctx.db.write() as session:
        if session.get(WebhookEvent, event_id) is not None:
            return JSONResponse({"received": True, "duplicate": True})
        record = WebhookEvent(
            event_id=event_id,
            provider_id=provider_id,
            received_at=now,
            payload_hash=sha256_ref(raw),
            processed=False,
        )
        session.add(record)
        payload = _parse(raw)
        try:
            payment = ctx.payments.apply_provider_event(
                session,
                provider_id=provider_id,
                event=payload["event"],
                payment_id=payload["payment_id"],
                uetr=payload["uetr"],
            )
        except errors.ApiError as err:
            record.processed = True
            record.outcome = f"rejected:{err.code}"
            ctx.audit.append(
                session,
                actor_type=ActorType.PROVIDER,
                actor_id=provider_id,
                action="webhook.rejected",
                payment_id=payload["payment_id"],
                decision=Decision.BLOCKED,
                reason_code=err.code,
                input_hash=sha256_ref(raw),
            )
            err.persist = True
            raise
        record.processed = True
        record.outcome = "applied"
        ctx.audit.append(
            session,
            actor_type=ActorType.PROVIDER,
            actor_id=provider_id,
            action="webhook.accepted",
            payment_id=payment.id,
            decision=Decision.APPROVED,
            reason_code=payload["event"],
            input_hash=sha256_ref(raw),
        )
    return JSONResponse({"received": True})


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise errors.BadRequest("The webhook body is not valid JSON.") from exc
    ok = (
        isinstance(payload, dict)
        and payload.get("event") in _EVENTS
        and isinstance(payload.get("payment_id"), str)
        and isinstance(payload.get("uetr"), str)
        and is_valid_uetr(payload["uetr"])
    )
    if not ok:
        raise errors.ValidationFailed("The webhook body is missing event, payment_id or uetr.")
    return payload  # type: ignore[no-any-return]


@router.post("/webhooks/provider")
async def provider_webhook(request: Request, ctx: AppContext = Depends(get_ctx)) -> JSONResponse:
    raw = await request.body()  # the RAW bytes: verified before any JSON parsing
    return await run_in_threadpool(
        _handle,
        ctx,
        raw,
        request.headers.get("x-signature"),
        request.headers.get("x-event-id"),
        client_ip(request),
    )
