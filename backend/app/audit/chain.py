"""Hash chain primitives (blueprint 15.2). Pure functions, no database.

this_event_hash = SHA256(prev_event_hash + canonical(event without this_event_hash))
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.crypto import canonical_json, sha256_hex

GENESIS = "0" * 64

HASHED_FIELDS = (
    "event_id",
    "seq",
    "timestamp",
    "actor_type",
    "actor_id",
    "action",
    "payment_id",
    "quote_id",
    "amount_minor",
    "currency",
    "recipient_id",
    "decision",
    "reason_code",
    "detail",
    "input_hash",
    "output_hash",
    "model_version",
    "prev_event_hash",
)


def canonical(event: Mapping[str, Any]) -> bytes:
    """JSON of the event WITHOUT this_event_hash: sorted keys, no whitespace, UTF-8."""
    return canonical_json({k: v for k, v in event.items() if k != "this_event_hash"})


def compute_hash(prev_hash: str, event: Mapping[str, Any]) -> str:
    return sha256_hex(prev_hash.encode("utf-8") + canonical(event))


@dataclass(frozen=True)
class ChainResult:
    ok: bool
    events_checked: int
    failed_seq: int | None = None
    reason: str | None = None
    last_seq: int = 0
    last_hash: str = GENESIS


def verify_events(events: Iterable[Mapping[str, Any]]) -> ChainResult:
    """Walk events in seq order and report the first break in the chain."""
    prev = GENESIS
    expected_seq = 1
    checked = 0
    for event in events:
        seq = int(event["seq"])
        if seq != expected_seq:
            return ChainResult(False, checked, expected_seq, "SEQ_GAP", expected_seq - 1, prev)
        if event["prev_event_hash"] != prev:
            return ChainResult(False, checked, seq, "PREV_HASH_MISMATCH", seq - 1, prev)
        if compute_hash(prev, event) != event["this_event_hash"]:
            return ChainResult(False, checked, seq, "HASH_MISMATCH", seq - 1, prev)
        prev = str(event["this_event_hash"])
        expected_seq += 1
        checked += 1
    return ChainResult(True, checked, None, None, expected_seq - 1, prev)
