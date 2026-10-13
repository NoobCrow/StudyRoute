"""Authentication: argon2id passwords, ES256 access tokens, rotating refresh tokens, MFA.

No custom crypto: argon2-cffi, PyJWT with the cryptography backend, and pyotp (RFC 6238).
Time always comes from the injected Clock, so expiry is testable.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import errors
from app.core.crypto import FieldCipher, constant_time_equals, sha256_hex
from app.core.ids import new_id
from app.domain.constants import ActorKind
from app.domain.rbac import ROLE_PERMISSIONS, Actor, make_actor
from app.models import MfaProof, RefreshToken, User

MFA_SCOPES = ("approve_payment", "allowlist_recipient")
TOTP_STEP_SECONDS = 30


class PasswordService:
    def __init__(self, time_cost: int = 2, memory_kib: int = 19456, parallelism: int = 1) -> None:
        # argon2id; the defaults follow the OWASP minimum (19 MiB, 2 iterations, 1 lane)
        self._hasher = PasswordHasher(
            time_cost=time_cost, memory_cost=memory_kib, parallelism=parallelism
        )
        self._dummy = self._hasher.hash("studyroute-timing-equaliser")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, stored_hash: str | None, password: str) -> bool:
        """Constant-ish time: an unknown user still costs one argon2 verification."""
        target = stored_hash or self._dummy
        try:
            matched = self._hasher.verify(target, password)
        except (VerificationError, InvalidHashError):
            return False
        return bool(matched) and stored_hash is not None


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    kind: ActorKind
    scopes: frozenset[str]
    token_id: str
    expires_at: datetime
    act_for: str | None


class TokenService:
    def __init__(
        self, private_pem: str, public_pem: str, issuer: str, audience: str, ttl_seconds: int
    ) -> None:
        self._private = private_pem
        self._public = public_pem
        self._issuer = issuer
        self._audience = audience
        self._ttl = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def issue(
        self,
        *,
        user_id: str,
        kind: ActorKind,
        scopes: frozenset[str],
        now: datetime,
        act_for: str | None = None,
    ) -> tuple[str, datetime]:
        expires = now + timedelta(seconds=self._ttl)
        claims: dict[str, Any] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": user_id,
            "role": kind.value,
            "scope": " ".join(sorted(scopes)),
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": new_id("jti"),
        }
        if act_for:
            claims["act_for"] = act_for
        token = jwt.encode(claims, self._private, algorithm="ES256", headers={"kid": "sandbox-1"})
        return token, expires

    def decode(self, token: str, now: datetime) -> TokenClaims:
        try:
            claims = jwt.decode(
                token,
                self._public,
                algorithms=["ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={
                    "require": ["exp", "iat", "sub", "jti", "role"],
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                },
            )
        except jwt.PyJWTError as exc:
            raise errors.Unauthenticated("Invalid or malformed access token.") from exc
        expires = datetime.fromtimestamp(int(claims["exp"]), tz=now.tzinfo)
        if now >= expires:
            raise errors.Unauthenticated("The access token has expired.")
        try:
            kind = ActorKind(claims["role"])
        except ValueError as exc:
            raise errors.Unauthenticated("Unknown role in token.") from exc
        return TokenClaims(
            user_id=str(claims["sub"]),
            kind=kind,
            scopes=frozenset(str(claims.get("scope", "")).split()),
            token_id=str(claims["jti"]),
            expires_at=expires,
            act_for=claims.get("act_for"),
        )


def household_owner_id(user: User) -> str | None:
    """Resources belong to the paying parent: a student maps to their parent."""
    if user.role == ActorKind.PARENT.value:
        return user.id
    if user.role == ActorKind.STUDENT.value:
        return user.parent_id
    return None


def human_actor(user: User, claims: TokenClaims | None = None) -> Actor:
    kind = ActorKind(user.role)
    scopes = claims.scopes & {p.value for p in ROLE_PERMISSIONS[kind]} if claims else None
    return make_actor(
        kind,
        user.id,
        owner_id=household_owner_id(user),
        scopes=scopes,
        token_id=claims.token_id if claims else None,
    )


def ai_actor(ai_user_id: str, parent: User, claims: TokenClaims | None = None) -> Actor:
    allowed = frozenset(p.value for p in ROLE_PERMISSIONS[ActorKind.AI])
    scopes = (claims.scopes & allowed) if claims else allowed
    return make_actor(
        ActorKind.AI,
        ai_user_id,
        owner_id=parent.id,
        on_behalf_of=parent.id,
        scopes=scopes,
        token_id=claims.token_id if claims else None,
    )


# --- refresh tokens (opaque, rotated on every use, family revoked on reuse) ---------------
def _new_secret_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def issue_refresh_token(
    session: Session, user_id: str, now: datetime, ttl_seconds: int, family_id: str | None = None
) -> tuple[str, datetime]:
    raw = _new_secret_token("rt")
    expires = now + timedelta(seconds=ttl_seconds)
    session.add(
        RefreshToken(
            token_hash=sha256_hex(raw),
            user_id=user_id,
            family_id=family_id or new_id("fam"),
            created_at=now,
            expires_at=expires,
        )
    )
    session.flush()
    return raw, expires


def revoke_family(session: Session, family_id: str, now: datetime) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def rotate_refresh_token(
    session: Session, raw_token: str, now: datetime, ttl_seconds: int
) -> tuple[str, str, datetime]:
    """Exchange a refresh token for a new one. Returns (user_id, new_token, expiry)."""
    row = session.get(RefreshToken, sha256_hex(raw_token))
    if row is None or row.revoked_at is not None or now >= row.expires_at:
        raise errors.Unauthenticated("Invalid or expired refresh token.")
    if row.used_at is not None:
        revoke_family(session, row.family_id, now)
        raise errors.Unauthenticated("Refresh token reuse detected. Sign in again.", persist=True)
    row.used_at = now
    new_raw, expires = issue_refresh_token(session, row.user_id, now, ttl_seconds, row.family_id)
    return row.user_id, new_raw, expires


# --- lockout ------------------------------------------------------------------------------
def ensure_not_locked(until: datetime | None, now: datetime) -> None:
    if until is not None and now < until:
        wait = max(1, int((until - now).total_seconds()))
        raise errors.RateLimited(
            "Too many failed attempts. Try again later.", headers={"Retry-After": str(wait)}
        )


# --- MFA ----------------------------------------------------------------------------------
def totp_secret_new() -> str:
    return pyotp.random_base32()


def check_mfa_code(
    user: User, code: str, now: datetime, cipher: FieldCipher, sandbox_code: str | None
) -> str:
    """Return the method that matched ("SANDBOX_CODE" or "TOTP"), or raise MfaRequired."""
    if sandbox_code and constant_time_equals(code, sandbox_code):
        return "SANDBOX_CODE"
    if user.mfa_secret_enc:
        secret = cipher.decrypt(user.mfa_secret_enc, context=f"users.mfa_secret|{user.id}")
        totp = pyotp.TOTP(secret, interval=TOTP_STEP_SECONDS)
        current_step = int(now.timestamp()) // TOTP_STEP_SECONDS
        for step in (current_step - 1, current_step, current_step + 1):
            if step <= user.last_totp_step:
                continue  # RFC 6238 5.2: a code may be used only once
            if constant_time_equals(totp.at(step * TOTP_STEP_SECONDS), code):
                user.last_totp_step = step
                return "TOTP"
    raise errors.MfaRequired("That MFA code is not valid.")


def issue_mfa_proof(
    session: Session, user_id: str, scope: str, subject_id: str, now: datetime, ttl_seconds: int
) -> tuple[str, datetime]:
    raw = _new_secret_token("mfa")
    expires = now + timedelta(seconds=ttl_seconds)
    session.add(
        MfaProof(
            proof_hash=sha256_hex(raw),
            user_id=user_id,
            scope=scope,
            subject_id=subject_id,
            issued_at=now,
            expires_at=expires,
        )
    )
    session.flush()
    return raw, expires


def find_valid_mfa_proof(
    session: Session, *, raw: str | None, user_id: str, scope: str, subject_id: str, now: datetime
) -> MfaProof | None:
    """The proof must be this user's, for this action and subject, unused and unexpired."""
    if not raw:
        return None
    proof = session.get(MfaProof, sha256_hex(raw))
    if (
        proof is None
        or proof.user_id != user_id
        or proof.scope != scope
        or proof.subject_id != subject_id
        or proof.used_at is not None
        or now >= proof.expires_at
    ):
        return None
    return proof


def proof_reference(proof: MfaProof) -> str:
    """Short, non-secret handle for audit events."""
    return f"mfa:{proof.proof_hash[:12]}"


# --- user creation (seed script and tests) -----------------------------------------------
def create_user(
    session: Session,
    *,
    passwords: PasswordService,
    cipher: FieldCipher,
    now: datetime,
    email: str,
    display_name: str,
    role: ActorKind,
    password: str | None,
    address: str = "",
    parent_id: str | None = None,
    kyc_status: str = "NEEDS_DOCUMENTS",
    user_id: str | None = None,
) -> User:
    uid = user_id or new_id("usr")
    secret = totp_secret_new() if password else None
    user = User(
        id=uid,
        email=email.strip().lower(),
        display_name=display_name,
        address=address,
        role=role.value,
        password_hash=passwords.hash(password) if password else None,
        mfa_secret_enc=cipher.encrypt(secret, context=f"users.mfa_secret|{uid}")
        if secret
        else None,
        kyc_status=kyc_status,
        parent_id=parent_id,
        created_at=now,
    )
    session.add(user)
    session.flush()
    return user


def find_user_by_email(session: Session, email: str) -> User | None:
    return session.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()
