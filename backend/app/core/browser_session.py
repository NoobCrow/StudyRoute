"""Cookie-session helpers. Same-origin browser API; legacy bearer API remains independent.

The cookie is stable within its absolute lifetime, NOT a rotating refresh token. This
avoids simultaneous-tab rotation/replay races. Rotate on login; revoke on logout. Each
browser access JWT is bound to the cookie session and checked against server revocation.
"""

from __future__ import annotations

from datetime import timedelta
from secrets import token_urlsafe
from urllib.parse import urlsplit

from fastapi import Request, Response
from sqlalchemy.orm import Session

from app.api.context import AppContext
from app.core import errors
from app.core.clock import iso_utc
from app.core.crypto import sha256_hex
from app.domain.constants import ActorKind
from app.domain.rbac import ROLE_PERMISSIONS
from app.models import BrowserSession, User

COOKIE = "sr_browser_session"
COOKIE_PATH = "/api/v1"
BROWSER_HEADER = "X-StudyRoute-Browser"


def trusted_browser(request: Request, ctx: AppContext) -> None:
    # Required non-simple header + JSON fetch prevent forms/navigation from authenticating.
    # Origin is checked independently of CORS; proxy rewrites must preserve Origin.
    if request.headers.get(BROWSER_HEADER) != "1":
        raise errors.Forbidden("Use the same-origin StudyRoute browser client.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise errors.Forbidden("Cross-site browser authentication is not allowed.")
    origin = request.headers.get("origin", "")
    own = f"{request.url.scheme}://{request.url.netloc}"
    allowed = {own, *ctx.settings.cors_origin_list}
    if not origin or origin == "null" or origin not in allowed:
        raise errors.Forbidden("Browser authentication origin is not allowed.")
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise errors.Forbidden("Invalid browser origin.")


def secure_cookie(request: Request, ctx: AppContext) -> bool:
    return not ctx.settings.is_sandbox or request.url.scheme == "https"


def set_cookie(response: Response, request: Request, ctx: AppContext, raw: str) -> None:
    response.set_cookie(
        COOKIE,
        raw,
        max_age=ctx.settings.refresh_token_ttl_seconds,
        path=COOKIE_PATH,
        secure=secure_cookie(request, ctx),
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_cookie(response: Response, request: Request, ctx: AppContext) -> None:
    response.delete_cookie(
        COOKIE,
        path=COOKIE_PATH,
        secure=secure_cookie(request, ctx),
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


def active_session(session: Session, raw: str | None, ctx: AppContext) -> BrowserSession:
    row = session.get(BrowserSession, sha256_hex(raw)) if raw else None
    if row is None or row.revoked_at is not None or ctx.clock.now() >= row.expires_at:
        raise errors.Unauthenticated("Browser session expired. Sign in again.")
    return row


def revoke_previous(session: Session, request: Request, ctx: AppContext) -> None:
    raw = request.cookies.get(COOKIE)
    row = session.get(BrowserSession, sha256_hex(raw)) if raw else None
    if row and row.revoked_at is None:
        row.revoked_at = ctx.clock.now()


def create_session(session: Session, user: User, ctx: AppContext) -> tuple[str, BrowserSession]:
    raw = "bs_" + token_urlsafe(32)
    now = ctx.clock.now()
    row = BrowserSession(
        token_hash=sha256_hex(raw),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(seconds=ctx.settings.refresh_token_ttl_seconds),
    )
    session.add(row)
    session.flush()
    return raw, row


def access_for(user: User, row: BrowserSession, ctx: AppContext) -> dict:
    kind = ActorKind(user.role)
    token, expiry = ctx.tokens.issue(
        user_id=user.id,
        kind=kind,
        scopes=frozenset(p.value for p in ROLE_PERMISSIONS[kind]),
        now=ctx.clock.now(),
        browser_session=row.token_hash,
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": ctx.tokens.ttl_seconds,
        "expires_at": iso_utc(expiry),
        "session_expires_at": iso_utc(row.expires_at),
    }
