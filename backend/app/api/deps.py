"""FastAPI dependencies: the app context, the authenticated actor, permissions, rate limits."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, Header, Request

from app.api.context import AppContext
from app.core import errors
from app.domain.auth import ai_actor, human_actor
from app.domain.constants import ActorKind
from app.domain.rbac import Actor, Perm, authorize
from app.models import User


def get_ctx(request: Request) -> AppContext:
    ctx: AppContext = request.app.state.ctx
    return ctx


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def current_actor(request: Request, ctx: AppContext = Depends(get_ctx)) -> Actor:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise errors.Unauthenticated("Send an Authorization: Bearer <token> header.")
    claims = ctx.tokens.decode(token.strip(), ctx.clock.now())
    with ctx.db.read() as session:
        user = session.get(User, claims.user_id)
        if user is None or user.role != claims.kind.value:
            raise errors.Unauthenticated("The token does not match a known user.")
        if claims.kind is ActorKind.AI:
            parent = session.get(User, claims.act_for) if claims.act_for else None
            if parent is None or parent.role != ActorKind.PARENT.value:
                raise errors.Unauthenticated("The AI token has no valid parent to act for.")
            return ai_actor(user.id, parent, claims)
        return human_actor(user, claims)


def require(perm: Perm) -> Callable[..., Actor]:
    """Dependency factory: authenticate, then check the role AND the token scope."""

    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        authorize(actor, perm)
        return actor

    return dependency


def limit_ip(group: str) -> Callable[..., None]:
    def dependency(request: Request, ctx: AppContext = Depends(get_ctx)) -> None:
        ctx.limiter.check(group, client_ip(request))

    return dependency


def limit_user(group: str) -> Callable[..., None]:
    def dependency(actor: Actor = Depends(current_actor), ctx: AppContext = Depends(get_ctx)) -> None:
        ctx.limiter.check(group, actor.user_id)

    return dependency


def idempotency_key(idempotency_key: str | None = Header(default=None)) -> str:
    """Payment-creating POSTs must carry a UUID Idempotency-Key (blueprint 8.4)."""
    if not idempotency_key:
        raise errors.BadRequest("The Idempotency-Key header (a UUID) is required.")
    try:
        return str(UUID(idempotency_key.strip()))
    except ValueError as exc:
        raise errors.BadRequest("The Idempotency-Key must be a UUID.") from exc
