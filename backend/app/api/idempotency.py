"""Idempotency-Key handling (blueprint 8.4).

The key, the request fingerprint and the stored response are written in the SAME transaction
as the payment change. A retry with the same key and body replays the stored response; the
same key with a different body is refused.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.core import errors
from app.core.crypto import hash_object
from app.core.logging import request_id_var
from app.domain.rbac import Actor
from app.domain.rules import Rules, load_rules
from app.models import IdempotencyKey

Work = Callable[[Session, Rules], tuple[int, dict[str, Any]]]


def _replay(row: IdempotencyKey) -> JSONResponse:
    media = errors.PROBLEM_CONTENT_TYPE if row.response_status >= 400 else "application/json"
    return JSONResponse(
        json.loads(row.response_body),
        status_code=row.response_status,
        media_type=media,
        headers={"Idempotent-Replay": "true"},
    )


def _attempt(
    ctx: AppContext, actor: Actor, key: str, method: str, path: str, body: dict[str, Any], work: Work
) -> JSONResponse:
    now = ctx.clock.now()
    fingerprint = hash_object({"method": method, "path": path, "body": body})
    with ctx.db.write() as session:
        existing = session.get(IdempotencyKey, (actor.user_id, key))
        if existing is not None and existing.expires_at > now:
            if existing.request_hash != fingerprint:
                raise errors.IdempotencyKeyReused(
                    "This Idempotency-Key was already used with a different request."
                )
            return _replay(existing)
        if existing is not None:
            session.delete(existing)
            session.flush()
        rules = load_rules(session)
        expires = now + timedelta(hours=rules.idempotency_ttl_hours)

        def remember(status: int, payload: dict[str, Any]) -> None:
            session.add(
                IdempotencyKey(
                    user_id=actor.user_id,
                    key=key,
                    method=method,
                    path=path,
                    request_hash=fingerprint,
                    response_status=status,
                    response_body=json.dumps(payload),
                    created_at=now,
                    expires_at=expires,
                )
            )

        try:
            status, payload = work(session, rules)
        except errors.ApiError as err:
            if err.persist:  # the error committed real work (an audit event): replay it too
                remember(
                    err.status,
                    errors.problem_body(
                        status=err.status,
                        code=err.code,
                        title=err.title,
                        detail=err.detail,
                        request_id=request_id_var.get(),
                        extra=err.extra,
                    ),
                )
            raise
        remember(status, payload)
        return JSONResponse(payload, status_code=status)


def run_idempotent(
    ctx: AppContext,
    *,
    actor: Actor,
    key: str,
    method: str,
    path: str,
    body: dict[str, Any],
    work: Work,
) -> JSONResponse:
    """Run `work` once per (user, key). Retries replay the stored response."""
    for _ in range(2):
        try:
            return _attempt(ctx, actor, key, method, path, body, work)
        except IntegrityError:  # another request stored the same key first; look again
            continue
    raise errors.RequestInProgress("Another request with this key is still being processed.")
