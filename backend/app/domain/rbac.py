"""Roles, permissions and actors (blueprint 12.2). Checked in the domain, not only in the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.core import errors
from app.domain.constants import ActorKind, ActorType


class Perm(StrEnum):
    QUOTE_CREATE = "quotes:create"
    QUOTE_READ = "quotes:read"
    PAYMENT_READ = "payments:read"
    PAYMENT_CREATE_DRAFT = "payments:draft"
    PAYMENT_REQUEST_APPROVAL = "payments:request_approval"
    PAYMENT_APPROVE = "payments:approve"
    PAYMENT_CANCEL = "payments:cancel"
    PAYMENT_REJECT = "payments:reject"
    RECIPIENT_CREATE = "recipients:create"
    RECIPIENT_READ = "recipients:read"
    RECIPIENT_ALLOWLIST = "recipients:allowlist"
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    AUDIT_READ = "audit:read"
    AUDIT_VERIFY = "audit:verify"
    KYC_READ = "kyc:read"
    KYC_SUBMIT = "kyc:submit"
    KYC_REVIEW = "kyc:review"
    PLANNER_READ = "planner:read"
    CHECKLIST_READ = "checklist:read"
    CHAT_USE = "chat:use"
    MFA_ISSUE = "mfa:issue"
    DOCUMENT_READ = "documents:read"
    DOCUMENT_WRITE = "documents:write"
    DATA_RESET = "data:reset"
    SANDBOX_CONTROL = "sandbox:control"
    BANK_READ = "bank:read"
    BANK_TRANSFER = "bank:transfer"
    ESCROW_READ = "escrow:read"
    ESCROW_WRITE = "escrow:write"
    ESCROW_FREEZE = "escrow:freeze"
    CHAIN_READ = "chain:read"
    CHAIN_ANCHOR = "chain:anchor"


P = Perm

_COMMON = {P.CONFIG_READ, P.CHECKLIST_READ}

ROLE_PERMISSIONS: dict[ActorKind, frozenset[Perm]] = {
    ActorKind.PARENT: frozenset(
        _COMMON
        | {
            P.QUOTE_CREATE,
            P.QUOTE_READ,
            P.PAYMENT_READ,
            P.PAYMENT_CREATE_DRAFT,
            P.PAYMENT_REQUEST_APPROVAL,
            P.PAYMENT_APPROVE,
            P.PAYMENT_CANCEL,
            P.PAYMENT_REJECT,
            P.RECIPIENT_CREATE,
            P.RECIPIENT_READ,
            P.RECIPIENT_ALLOWLIST,
            P.AUDIT_READ,
            P.KYC_READ,
            P.KYC_SUBMIT,
            P.PLANNER_READ,
            P.CHAT_USE,
            P.MFA_ISSUE,
            P.DOCUMENT_READ,
            P.DOCUMENT_WRITE,
            P.DATA_RESET,
            P.BANK_READ,
            P.BANK_TRANSFER,
            P.ESCROW_READ,
            P.ESCROW_WRITE,
            P.CHAIN_READ,
        }
    ),
    ActorKind.STUDENT: frozenset(
        _COMMON
        | {
            P.QUOTE_CREATE,
            P.QUOTE_READ,
            P.PAYMENT_READ,
            P.RECIPIENT_CREATE,
            P.RECIPIENT_READ,
            P.KYC_READ,
            P.KYC_SUBMIT,
            P.PLANNER_READ,
            P.CHAT_USE,
            P.DOCUMENT_READ,
            P.DOCUMENT_WRITE,
            P.BANK_READ,
            P.ESCROW_READ,
            P.CHAIN_READ,
        }
    ),
    ActorKind.ADMIN: frozenset(
        _COMMON
        | {
            P.QUOTE_READ,
            P.PAYMENT_READ,
            P.PAYMENT_REJECT,
            P.RECIPIENT_READ,
            P.CONFIG_WRITE,
            P.AUDIT_READ,
            P.AUDIT_VERIFY,
            P.KYC_READ,
            P.KYC_REVIEW,
            P.SANDBOX_CONTROL,
            P.BANK_READ,
            P.ESCROW_READ,
            P.ESCROW_FREEZE,
            P.CHAIN_READ,
            P.CHAIN_ANCHOR,
        }
    ),
    ActorKind.AI: frozenset(
        _COMMON
        | {
            P.QUOTE_CREATE,
            P.QUOTE_READ,
            P.PAYMENT_READ,
            P.PAYMENT_CREATE_DRAFT,
            P.PAYMENT_REQUEST_APPROVAL,
            P.RECIPIENT_READ,
            P.KYC_READ,
            P.PLANNER_READ,
            P.DOCUMENT_READ,
        }
    ),
    ActorKind.SYSTEM: frozenset(),
    ActorKind.PROVIDER: frozenset(),
}


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    user_id: str
    owner_id: str | None
    scopes: frozenset[str] = field(default_factory=frozenset)
    on_behalf_of: str | None = None
    token_id: str | None = None

    @property
    def audit_type(self) -> ActorType:
        if self.kind is ActorKind.AI:
            return ActorType.AI
        if self.kind is ActorKind.SYSTEM:
            return ActorType.SYSTEM
        if self.kind is ActorKind.PROVIDER:
            return ActorType.PROVIDER
        return ActorType.USER

    def can_see_owner(self, owner_id: str) -> bool:
        """Parents, students and the AI see one household. Admins and the system see all."""
        return self.owner_id is None or owner_id == self.owner_id


def make_actor(
    kind: ActorKind,
    user_id: str,
    *,
    owner_id: str | None,
    on_behalf_of: str | None = None,
    scopes: frozenset[str] | None = None,
    token_id: str | None = None,
) -> Actor:
    granted = scopes if scopes is not None else frozenset(p.value for p in ROLE_PERMISSIONS[kind])
    return Actor(kind, user_id, owner_id, granted, on_behalf_of, token_id)


SYSTEM_ACTOR = Actor(ActorKind.SYSTEM, "system", None)


def provider_actor(provider_id: str) -> Actor:
    return Actor(ActorKind.PROVIDER, provider_id, None)


def authorize(actor: Actor, perm: Perm) -> None:
    """Raise unless both the role and the token scope grant `perm`."""
    if perm is Perm.PAYMENT_APPROVE and actor.kind is ActorKind.AI:
        raise errors.AiCannotApprove("The AI assistant can never approve a payment.")
    if perm not in ROLE_PERMISSIONS[actor.kind] or perm.value not in actor.scopes:
        raise errors.Forbidden("You do not have permission to do this.")
