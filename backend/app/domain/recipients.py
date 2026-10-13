"""Recipients: validation, encrypted storage, masked views and MFA-gated allowlisting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import FieldCipher, sha256_ref
from app.core.ids import new_id
from app.domain import auth
from app.domain.compliance import is_sanctions_hit
from app.domain.constants import Decision, RecipientType
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import Corridor, Rules
from app.engine import validators as v
from app.models import Recipient

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DIGITS = re.compile(r"\d{4,17}")
_ALNUM = re.compile(r"[A-Za-z0-9]{4,34}")


@dataclass(frozen=True)
class RecipientCreate:
    type: str
    display_name: str
    country: str
    bic: str
    iban: str | None = None
    account_number: str | None = None
    routing_code: str | None = None


@dataclass(frozen=True)
class NormalizedAccount:
    kind: str
    identifier: str
    routing_code: str | None


def clean_name(raw: str) -> str:
    """Strip control characters and collapse whitespace. HTML is kept: the UI escapes it."""
    name = re.sub(r"\s+", " ", _CONTROL.sub(" ", raw)).strip()
    if not 2 <= len(name) <= 120:
        raise errors.ValidationFailed("The recipient name must be 2 to 120 characters.")
    return name


def _iban_account(corridor: Corridor, raw: str) -> NormalizedAccount:
    iban = v.normalize_iban(raw)
    if not v.is_valid_iban(iban):
        raise errors.InvalidIban("The IBAN failed its length or checksum check.")
    if iban[:2] != corridor.country:
        raise errors.ValidationFailed(f"The IBAN must be a {corridor.country} IBAN.")
    return NormalizedAccount("IBAN", iban, None)


def normalize_account(corridor: Corridor, payload: RecipientCreate) -> NormalizedAccount:
    scheme = corridor.account_scheme
    if scheme == "IBAN" or (scheme == "IBAN_OR_UK_DOMESTIC" and payload.iban):
        if not payload.iban:
            raise errors.ValidationFailed(f"An IBAN is required for {corridor.name}.")
        return _iban_account(corridor, payload.iban)
    account = re.sub(r"[\s-]", "", payload.account_number or "")
    routing = re.sub(r"[\s-]", "", payload.routing_code or "") or None
    if scheme == "IBAN_OR_UK_DOMESTIC":
        if not (routing and v.is_valid_uk_sort_code(routing) and v.is_valid_uk_account(account)):
            raise errors.ValidationFailed(
                "Give a valid IBAN, or a 6-digit sort code and an 8-digit account number."
            )
        return NormalizedAccount("ACCOUNT", account, routing)
    if scheme == "ABA_ACCOUNT":
        if not (routing and v.is_valid_aba(routing)):
            raise errors.ValidationFailed("The ABA routing number failed its checksum.")
        if not _DIGITS.fullmatch(account):
            raise errors.ValidationFailed("The account number must be 4 to 17 digits.")
        return NormalizedAccount("ACCOUNT", account, routing)
    if not _ALNUM.fullmatch(account):
        raise errors.ValidationFailed("The account number must be 4 to 34 letters or digits.")
    return NormalizedAccount("ACCOUNT", account, routing)


def validate_bic(corridor: Corridor, bic: str) -> str:
    cleaned = bic.strip().upper()
    if not v.is_valid_bic(cleaned):
        raise errors.InvalidBic("The BIC must be 8 or 11 letters and digits.")
    if cleaned[4:6] != corridor.country:
        raise errors.ValidationFailed(f"The BIC country must be {corridor.country}.")
    return cleaned


class RecipientService:
    def __init__(self, clock: Clock, audit: AuditService, cipher: FieldCipher) -> None:
        self._clock = clock
        self._audit = audit
        self._cipher = cipher

    # --- reading ----------------------------------------------------------------------
    def get_owned(self, session: Session, actor: Actor, recipient_id: str) -> Recipient:
        row = session.get(Recipient, recipient_id)
        if row is None or not actor.can_see_owner(row.owner_id):
            raise errors.NotFound("Recipient not found.")
        return row

    def list(self, session: Session, actor: Actor) -> list[Recipient]:
        authorize(actor, Perm.RECIPIENT_READ)
        stmt = select(Recipient).order_by(Recipient.created_at.desc())
        if actor.owner_id is not None:
            stmt = stmt.where(Recipient.owner_id == actor.owner_id)
        return list(session.execute(stmt).scalars())

    def _decrypt(self, row: Recipient) -> str:
        return self._cipher.decrypt(row.iban_or_account_enc, context=f"recipients.account|{row.id}")

    def account_mask(self, row: Recipient) -> str:
        return v.mask_account(self._decrypt(row), row.country)

    def label(self, row: Recipient) -> str:
        return f"{row.display_name} {self.account_mask(row)}"

    def view(self, row: Recipient) -> dict[str, Any]:
        return {
            "recipient_id": row.id,
            "type": row.type,
            "display_name": row.display_name,
            "country": row.country,
            "bic": row.bic,
            "account_kind": row.account_kind,
            "account_masked": self.account_mask(row),
            "routing_code": row.routing_code,
            "label": self.label(row),
            "allowlisted": row.allowlisted,
            "allowlisted_at": iso_utc(row.allowlisted_at) if row.allowlisted_at else None,
            "created_at": iso_utc(row.created_at),
        }

    # --- writing ----------------------------------------------------------------------
    def block_if_sanctioned(
        self, session: Session, actor: Actor, rules: Rules, name: str, recipient_id: str | None
    ) -> None:
        if not is_sanctions_hit(rules, name):
            return
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="compliance.blocked",
            recipient_id=recipient_id,
            decision=Decision.BLOCKED,
            reason_code="SANCTIONS_HIT",
            input_hash=sha256_ref(name),
        )
        raise errors.SanctionsHit(
            "This recipient matched the mock sanctions screening and was blocked.", persist=True
        )

    def create(
        self, session: Session, actor: Actor, rules: Rules, payload: RecipientCreate
    ) -> Recipient:
        authorize(actor, Perm.RECIPIENT_CREATE)
        if actor.owner_id is None:
            raise errors.Forbidden("Recipients belong to a paying parent.")
        if payload.type not in {t.value for t in RecipientType}:
            raise errors.ValidationFailed("Recipient type must be UNIVERSITY or STUDENT.")
        corridor = rules.corridor(payload.country)
        name = clean_name(payload.display_name)
        self.block_if_sanctioned(session, actor, rules, name, None)
        account = normalize_account(corridor, payload)
        bic = validate_bic(corridor, payload.bic)
        now = self._clock.now()
        rid = new_id("rcp")
        row = Recipient(
            id=rid,
            owner_id=actor.owner_id,
            created_by=actor.user_id,
            type=payload.type,
            display_name=name,
            country=corridor.country,
            bic=bic,
            account_kind=account.kind,
            routing_code=account.routing_code,
            iban_or_account_enc=self._cipher.encrypt(
                account.identifier, context=f"recipients.account|{rid}"
            ),
            account_last4=v.last4(account.identifier),
            allowlisted=False,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="recipient.created",
            recipient_id=rid,
            detail=f"{payload.type} {corridor.country} account ending {row.account_last4}",
        )
        return row

    def update(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        recipient_id: str,
        *,
        display_name: str | None,
        allowlisted: bool | None,
        mfa_proof_raw: str | None,
    ) -> Recipient:
        authorize(actor, Perm.RECIPIENT_ALLOWLIST)
        row = self.get_owned(session, actor, recipient_id)
        now = self._clock.now()
        proof = auth.find_valid_mfa_proof(
            session,
            raw=mfa_proof_raw,
            user_id=actor.user_id,
            scope="allowlist_recipient",
            subject_id=row.id,
            now=now,
        )
        if proof is None:
            self._audit.append(
                session,
                actor_type=actor.audit_type,
                actor_id=actor.user_id,
                action="recipient.update_blocked",
                recipient_id=row.id,
                decision=Decision.BLOCKED,
                reason_code="MFA_REQUIRED",
            )
            raise errors.MfaRequired(
                "Verify MFA for this recipient first (the proof lasts 5 minutes).", persist=True
            )
        if display_name is None and allowlisted is None:
            raise errors.ValidationFailed("Nothing to change: send display_name or allowlisted.")
        changes: list[str] = []
        if display_name is not None:
            name = clean_name(display_name)
            self.block_if_sanctioned(session, actor, rules, name, row.id)
            if name != row.display_name:
                row.display_name = name
                row.allowlisted = False
                row.allowlisted_by = None
                row.allowlisted_at = None
                changes.append("renamed (allowlist reset)")
        if allowlisted is not None and allowlisted != row.allowlisted:
            row.allowlisted = allowlisted
            row.allowlisted_by = actor.user_id if allowlisted else None
            row.allowlisted_at = now if allowlisted else None
            changes.append("allowlisted" if allowlisted else "removed from allowlist")
        row.updated_at = now
        proof.used_at = now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="recipient.allowlisted" if row.allowlisted else "recipient.updated",
            recipient_id=row.id,
            decision=Decision.APPROVED if row.allowlisted else None,
            reason_code=auth.proof_reference(proof),
            detail="; ".join(changes) or "no change",
        )
        session.flush()
        return row
