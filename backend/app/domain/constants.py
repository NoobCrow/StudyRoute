"""Shared enumerations. Plain strings in the database, enums in code."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    PARENT = "parent"
    STUDENT = "student"
    ADMIN = "admin"
    AI = "ai"


class KycStatus(StrEnum):
    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    NEEDS_DOCUMENTS = "NEEDS_DOCUMENTS"


class PaymentState(StrEnum):
    DRAFT = "DRAFT"
    QUOTED = "QUOTED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    SETTLED = "SETTLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


TERMINAL_STATES = frozenset(
    {
        PaymentState.SETTLED,
        PaymentState.REJECTED,
        PaymentState.CANCELLED,
        PaymentState.FAILED,
    }
)


class RecipientType(StrEnum):
    UNIVERSITY = "UNIVERSITY"
    STUDENT = "STUDENT"


class ActorType(StrEnum):
    USER = "user"
    AI = "ai"
    SYSTEM = "system"
    PROVIDER = "provider"


class Decision(StrEnum):
    SUGGESTED = "suggested"
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class Purpose(StrEnum):
    TUITION = "TUITION"
    LIVING = "LIVING"


def sql_in(values: type[StrEnum]) -> str:
    """Render enum values as a SQL IN list for CHECK constraints."""
    return ", ".join(f"'{member.value}'" for member in values)
