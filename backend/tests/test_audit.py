"""Audit log: append-only, hash-chained, tamper-evident (blueprint 15, test T16)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.audit.chain import GENESIS, canonical, compute_hash, verify_events
from app.audit.service import AuditService
from app.core.clock import FakeClock
from app.core.db import Database
from app.scripts.tamper_audit import restore_row, tamper_row


def make_chain(count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    prev = GENESIS
    for seq in range(1, count + 1):
        event: dict[str, Any] = {
            "event_id": f"aud_{seq}",
            "seq": seq,
            "timestamp": f"2026-10-14T05:00:{seq:02d}.000000Z",
            "actor_type": "user",
            "actor_id": "usr_1",
            "action": "quote.created",
            "payment_id": None,
            "quote_id": f"qte_{seq}",
            "amount_minor": seq * 100,
            "currency": "GBP",
            "recipient_id": None,
            "decision": None,
            "reason_code": None,
            "input_hash": None,
            "output_hash": None,
            "model_version": None,
            "prev_event_hash": prev,
        }
        event["this_event_hash"] = compute_hash(prev, event)
        prev = event["this_event_hash"]
        events.append(event)
    return events


def test_canonical_is_sorted_compact_utf8_and_excludes_the_event_hash() -> None:
    event = {"b": 1, "a": "é", "this_event_hash": "zzz"}
    assert canonical(event) == '{"a":"é","b":1}'.encode()


def test_hash_is_sha256_of_prev_plus_canonical() -> None:
    import hashlib

    event = {"a": 1}
    expected = hashlib.sha256((GENESIS + '{"a":1}').encode()).hexdigest()
    assert compute_hash(GENESIS, event) == expected


def test_pure_chain_verifies_and_pinpoints_a_tampered_event() -> None:
    chain = make_chain(6)
    assert verify_events(chain).ok
    chain[3]["amount_minor"] = 999
    result = verify_events(chain)
    assert not result.ok
    assert result.failed_seq == 4
    assert result.reason == "HASH_MISMATCH"


def test_pure_chain_detects_a_broken_link_a_gap_and_reordering() -> None:
    chain = make_chain(5)
    broken = [dict(e) for e in chain]
    broken[2]["prev_event_hash"] = "f" * 64
    assert verify_events(broken).failed_seq == 3

    gap = chain[:2] + chain[3:]
    assert verify_events(gap).failed_seq == 3
    assert verify_events(gap).reason == "SEQ_GAP"

    swapped = [chain[0], chain[2], chain[1], chain[3], chain[4]]
    assert not verify_events(swapped).ok


def test_empty_log_passes() -> None:
    assert verify_events([]).ok


def append_n(db: Database, clock: FakeClock, count: int) -> None:
    audit = AuditService(clock)
    for index in range(count):
        with db.write() as session:
            audit.append(
                session,
                actor_type="user",
                actor_id="usr_1",
                action="quote.created",
                quote_id=f"qte_{index}",
                amount_minor=1000 + index,
                currency="GBP",
            )


def test_appended_events_link_up_and_verify(db: Database, clock: FakeClock) -> None:
    append_n(db, clock, 5)
    with db.read() as session:
        result = AuditService(clock).verify(session)
    assert result.ok
    assert result.events_checked == 5
    assert result.head_seq == 5


def test_audit_event_rolls_back_with_its_transaction(db: Database, clock: FakeClock) -> None:
    audit = AuditService(clock)
    with pytest.raises(RuntimeError), db.write() as session:
        audit.append(session, actor_type="system", actor_id="sys", action="payment.created")
        raise RuntimeError("business step failed")
    with db.read() as session:
        assert audit.verify(session).events_checked == 0


def test_T16_editing_one_row_makes_verify_fail_at_that_sequence(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    append_n(db, clock, 6)
    tamper_row(db_path, seq=4)
    with db.read() as session:
        result = AuditService(clock).verify(session)
    assert not result.ok
    assert result.failed_seq == 4
    assert result.reason == "HASH_MISMATCH"
    assert result.to_api_dict()["status"] == "FAIL"

    restore_row(db_path)
    with db.read() as session:
        assert AuditService(clock).verify(session).ok


def test_application_role_cannot_update_or_delete_audit_rows(
    db: Database, clock: FakeClock
) -> None:
    append_n(db, clock, 2)
    with pytest.raises(IntegrityError), db.write() as session:
        session.execute(text("UPDATE audit_events SET action = 'x' WHERE seq = 1"))
    with pytest.raises(IntegrityError), db.write() as session:
        session.execute(text("DELETE FROM audit_events WHERE seq = 2"))


def test_truncating_the_tail_is_detected_through_the_head_pointer(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    import sqlite3

    append_n(db, clock, 5)
    con = sqlite3.connect(db_path)
    con.execute("DROP TRIGGER audit_events_no_delete")
    con.execute("DELETE FROM audit_events WHERE seq = 5")
    con.commit()
    con.close()
    with db.read() as session:
        result = AuditService(clock).verify(session)
    assert not result.ok
    assert result.reason == "HEAD_MISMATCH"
    assert result.failed_seq == 5


def test_verify_can_compare_against_an_externally_published_head(
    db: Database, clock: FakeClock
) -> None:
    append_n(db, clock, 3)
    audit = AuditService(clock)
    with db.read() as session:
        head = audit.verify(session).head_hash
        assert audit.verify(session, expected_head=head).ok
        wrong = audit.verify(session, expected_head="0" * 64)
    assert not wrong.ok
    assert wrong.reason == "EXTERNAL_HEAD_MISMATCH"


def test_concurrent_writers_keep_one_linear_chain(db: Database, clock: FakeClock) -> None:
    audit = AuditService(clock)
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            for index in range(15):
                with db.write() as session:
                    audit.append(
                        session,
                        actor_type="user",
                        actor_id=name,
                        action="quote.created",
                        quote_id=f"{name}-{index}",
                    )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"usr_{n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    with db.read() as session:
        result = audit.verify(session)
    assert result.ok
    assert result.events_checked == 60
