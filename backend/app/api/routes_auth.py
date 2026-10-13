"""Authentication endpoints: login, refresh, logout, MFA step-up and /me."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends

from app.api.context import AppContext
from app.api.deps import current_actor, get_ctx, limit_ip, require
from app.api.schemas import LoginIn, MfaVerifyIn, RefreshIn
from app.core import errors
from app.core.clock import iso_utc
from app.core.crypto import sha256_hex, sha256_ref
from app.domain import auth
from app.domain.constants import ActorKind, ActorType, Decision
from app.domain.rbac import ROLE_PERMISSIONS, Actor, Perm
from app.domain.rules import load_rules
from app.models import Payment, Recipient, RefreshToken, User

router = APIRouter(tags=["auth"])


def _user_view(user: User, payer: User | None) -> dict[str, Any]:
    kind = ActorKind(user.role)
    return {
        "user_id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "kyc_status": (payer or user).kyc_status if kind is not ActorKind.ADMIN else None,
        "payer": {"user_id": payer.id, "display_name": payer.display_name} if payer else None,
        "permissions": sorted(p.value for p in ROLE_PERMISSIONS[kind]),
    }


def _issue_tokens(ctx: AppContext, session: Any, user: User, family: str | None = None) -> dict[str, Any]:
    now = ctx.clock.now()
    kind = ActorKind(user.role)
    scopes = frozenset(p.value for p in ROLE_PERMISSIONS[kind])
    access, expires = ctx.tokens.issue(user_id=user.id, kind=kind, scopes=scopes, now=now)
    refresh, refresh_expires = auth.issue_refresh_token(
        session, user.id, now, ctx.settings.refresh_token_ttl_seconds, family
    )
    return {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": ctx.tokens.ttl_seconds,
        "expires_at": iso_utc(expires),
        "refresh_token": refresh,
        "refresh_expires_at": iso_utc(refresh_expires),
    }


def _payer_of(session: Any, user: User) -> User | None:
    owner_id = auth.household_owner_id(user)
    return session.get(User, owner_id) if owner_id else None


@router.post("/auth/login")
def login(
    body: LoginIn, ctx: AppContext = Depends(get_ctx), _: None = Depends(limit_ip("auth"))
) -> dict[str, Any]:
    now = ctx.clock.now()
    settings = ctx.settings
    with ctx.db.write() as session:
        user = auth.find_user_by_email(session, body.email)
        if user is not None:
            auth.ensure_not_locked(user.locked_until, now)
        good = ctx.passwords.verify(user.password_hash if user else None, body.password)
        if user is None or not good or user.role == ActorKind.AI.value:
            if user is not None:
                user.failed_logins += 1
                if user.failed_logins >= settings.max_failed_logins:
                    user.failed_logins = 0
                    user.locked_until = now + timedelta(seconds=settings.lockout_seconds)
            ctx.audit.append(
                session,
                actor_type=ActorType.USER,
                actor_id=user.id if user else "anonymous",
                action="auth.failed",
                decision=Decision.BLOCKED,
                reason_code="BAD_CREDENTIALS",
                input_hash=sha256_ref(body.email.strip().lower()),
            )
            raise errors.Unauthenticated("Invalid email or password.", persist=True)
        user.failed_logins = 0
        user.locked_until = None
        tokens = _issue_tokens(ctx, session, user)
        ctx.audit.append(
            session,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="auth.login",
            decision=Decision.APPROVED,
        )
        return {**tokens, "user": _user_view(user, _payer_of(session, user))}


@router.post("/auth/refresh")
def refresh(
    body: RefreshIn, ctx: AppContext = Depends(get_ctx), _: None = Depends(limit_ip("auth"))
) -> dict[str, Any]:
    now = ctx.clock.now()
    with ctx.db.write() as session:
        user_id, new_refresh, refresh_expires = auth.rotate_refresh_token(
            session, body.refresh_token, now, ctx.settings.refresh_token_ttl_seconds
        )
        user = session.get(User, user_id)
        if user is None:
            raise errors.Unauthenticated("Unknown user.")
        kind = ActorKind(user.role)
        scopes = frozenset(p.value for p in ROLE_PERMISSIONS[kind])
        access, expires = ctx.tokens.issue(user_id=user.id, kind=kind, scopes=scopes, now=now)
        return {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": ctx.tokens.ttl_seconds,
            "expires_at": iso_utc(expires),
            "refresh_token": new_refresh,
            "refresh_expires_at": iso_utc(refresh_expires),
        }


@router.post("/auth/logout")
def logout(
    body: RefreshIn, ctx: AppContext = Depends(get_ctx), _: None = Depends(limit_ip("auth"))
) -> dict[str, Any]:
    with ctx.db.write() as session:
        row = session.get(RefreshToken, sha256_hex(body.refresh_token))
        if row is not None:
            auth.revoke_family(session, row.family_id, ctx.clock.now())
    return {"signed_out": True}


@router.get("/me")
def me(actor: Actor = Depends(current_actor), ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    with ctx.db.read() as session:
        user = session.get(User, actor.user_id)
        if user is None:
            raise errors.Unauthenticated("Unknown user.")
        return _user_view(user, _payer_of(session, user))


@router.post("/auth/mfa/verify")
def mfa_verify(
    body: MfaVerifyIn,
    actor: Actor = Depends(require(Perm.MFA_ISSUE)),
    ctx: AppContext = Depends(get_ctx),
    _: None = Depends(limit_ip("auth")),
) -> dict[str, Any]:
    """Step-up MFA. Returns a proof valid for 5 minutes, bound to this user and this subject."""
    now = ctx.clock.now()
    settings = ctx.settings
    if body.scope not in auth.MFA_SCOPES:
        raise errors.ValidationFailed(f"Scope must be one of: {', '.join(auth.MFA_SCOPES)}.")
    with ctx.db.write() as session:
        user = session.get(User, actor.user_id)
        if user is None:
            raise errors.Unauthenticated("Unknown user.")
        auth.ensure_not_locked(user.mfa_locked_until, now)
        subject = (
            session.get(Payment, body.subject_id)
            if body.scope == "approve_payment"
            else session.get(Recipient, body.subject_id)
        )
        if subject is None or not actor.can_see_owner(subject.owner_id):
            raise errors.NotFound("The subject of the MFA step was not found.")
        try:
            method = auth.check_mfa_code(user, body.code, now, ctx.cipher, settings.sandbox_mfa_code)
        except errors.MfaRequired:
            user.failed_mfa += 1
            if user.failed_mfa >= settings.max_failed_mfa:
                user.failed_mfa = 0
                user.mfa_locked_until = now + timedelta(seconds=settings.mfa_lockout_seconds)
            ctx.audit.append(
                session,
                actor_type=ActorType.USER,
                actor_id=user.id,
                action="auth.failed",
                decision=Decision.BLOCKED,
                reason_code="MFA_BAD_CODE",
                detail=body.scope,
            )
            raise errors.MfaRequired("That MFA code is not valid.", persist=True) from None
        user.failed_mfa = 0
        ttl = load_rules(session).mfa_proof_ttl_seconds
        proof, expires = auth.issue_mfa_proof(session, user.id, body.scope, subject.id, now, ttl)
        ctx.audit.append(
            session,
            actor_type=ActorType.USER,
            actor_id=user.id,
            action="auth.mfa",
            decision=Decision.APPROVED,
            reason_code=method,
            detail=f"{body.scope} for {subject.id}",
        )
        return {
            "mfa_proof": proof,
            "expires_at": iso_utc(expires),
            "valid_seconds": ttl,
            "scope": body.scope,
            "subject_id": subject.id,
            "method": method,
        }
