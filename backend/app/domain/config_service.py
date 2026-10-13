"""Admin changes to the rules table, always audited with who, what and why."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core.clock import Clock
from app.core.crypto import hash_object
from app.domain.rbac import Actor, Perm, authorize
from app.domain.rules import RuleRecord, update_rule


def _short(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


class ConfigService:
    def __init__(self, clock: Clock, audit: AuditService) -> None:
        self._clock = clock
        self._audit = audit

    def update(
        self,
        session: Session,
        actor: Actor,
        *,
        key: str,
        value: Any,
        source_url: str | None,
        verified: bool,
        reason: str,
    ) -> RuleRecord:
        authorize(actor, Perm.CONFIG_WRITE)
        before, after = update_rule(
            session,
            key=key,
            value=value,
            source_url=source_url,
            verified=verified,
            reason=reason,
            updated_by=actor.user_id,
            now=self._clock.now(),
        )
        change = f"{_short(before.value)} -> {_short(after.value)}"
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="config.changed",
            reason_code=key[:64],
            detail=f"{change}; verified={after.verified}; why: {reason.strip()}",
            input_hash=hash_object({"key": key, "value": before.value, "v": before.verified}),
            output_hash=hash_object({"key": key, "value": after.value, "v": after.verified}),
        )
        return after
