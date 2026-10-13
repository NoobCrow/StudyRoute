"""Append-only audit service. Events are written in the caller's transaction."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.chain import (
    GENESIS,
    HASHED_FIELDS,
    ChainResult,
    compute_hash,
    verify_events,
)
from app.core.clock import Clock
from app.core.ids import new_id
from app.models import AuditEvent, AuditHead

_TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_BATCH = 500


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    events_checked: int
    failed_seq: int | None
    reason: str | None
    head_seq: int
    head_hash: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.ok else "FAIL",
            "events_checked": self.events_checked,
            "failed_seq": self.failed_seq,
            "reason": self.reason,
            "head": {"seq": self.head_seq, "hash": self.head_hash},
        }


def event_dict(row: AuditEvent) -> dict[str, Any]:
    """The hashed view of a stored event, plus its hash."""
    data = {name: getattr(row, name) for name in HASHED_FIELDS}
    data["this_event_hash"] = row.this_event_hash
    return data


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


class AuditService:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    def ensure_head(self, session: Session) -> AuditHead:
        head = session.get(AuditHead, 1)
        if head is None:
            head = AuditHead(id=1, seq=0, hash=GENESIS)
            session.add(head)
            session.flush()
        return head

    def append(
        self,
        session: Session,
        *,
        actor_type: Any,
        actor_id: str,
        action: str,
        payment_id: str | None = None,
        quote_id: str | None = None,
        amount_minor: int | None = None,
        currency: str | None = None,
        recipient_id: str | None = None,
        decision: Any = None,
        reason_code: str | None = None,
        detail: str | None = None,
        input_hash: str | None = None,
        output_hash: str | None = None,
        model_version: str | None = None,
    ) -> AuditEvent:
        """Add one event to the chain inside the caller's open transaction."""
        head = session.execute(
            select(AuditHead).where(AuditHead.id == 1).with_for_update()
        ).scalar_one_or_none()
        if head is None:
            head = self.ensure_head(session)
        row: dict[str, Any] = {
            "event_id": new_id("aud"),
            "seq": head.seq + 1,
            "timestamp": self._clock.now().strftime(_TS_FORMAT),
            "actor_type": _plain(actor_type),
            "actor_id": actor_id,
            "action": action,
            "payment_id": payment_id[:64] if payment_id else None,
            "quote_id": quote_id,
            "amount_minor": amount_minor,
            "currency": currency,
            "recipient_id": recipient_id,
            "decision": _plain(decision),
            "reason_code": reason_code,
            "detail": detail[:240] if detail else None,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "model_version": model_version,
            "prev_event_hash": head.hash,
        }
        row["this_event_hash"] = compute_hash(head.hash, row)
        event = AuditEvent(**row)
        session.add(event)
        head.seq = row["seq"]
        head.hash = row["this_event_hash"]
        session.flush()
        return event

    def _stream(self, session: Session) -> Iterator[dict[str, Any]]:
        last = 0
        while True:
            rows = (
                session.execute(
                    select(AuditEvent)
                    .where(AuditEvent.seq > last)
                    .order_by(AuditEvent.seq)
                    .limit(_BATCH)
                )
                .scalars()
                .all()
            )
            if not rows:
                return
            for row in rows:
                yield event_dict(row)
            last = rows[-1].seq

    def verify(self, session: Session, *, expected_head: str | None = None) -> VerifyResult:
        """Recompute the whole chain, then check the head pointer and any published head."""
        chain: ChainResult = verify_events(self._stream(session))
        head = session.get(AuditHead, 1)
        head_seq = head.seq if head else 0
        head_hash = head.hash if head else GENESIS
        if not chain.ok:
            return VerifyResult(
                False, chain.events_checked, chain.failed_seq, chain.reason, head_seq, head_hash
            )
        if chain.last_seq != head_seq or chain.last_hash != head_hash:
            return VerifyResult(
                False,
                chain.events_checked,
                chain.last_seq + 1,
                "HEAD_MISMATCH",
                head_seq,
                head_hash,
            )
        if expected_head and expected_head != chain.last_hash:
            return VerifyResult(
                False,
                chain.events_checked,
                chain.last_seq,
                "EXTERNAL_HEAD_MISMATCH",
                head_seq,
                head_hash,
            )
        return VerifyResult(True, chain.events_checked, None, None, head_seq, head_hash)
