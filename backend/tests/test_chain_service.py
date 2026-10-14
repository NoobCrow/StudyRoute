"""The chain service: a hash-chained log that rebuilds the in-memory EVM exactly."""

from __future__ import annotations

import sqlite3
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from app.audit.chain import GENESIS
from app.audit.service import AuditService
from app.core import errors
from app.core.clock import FakeClock
from app.core.db import Database
from app.domain.chain_service import BANK, ESCROW, ChainService, user_wallet
from app.models import AuditEvent, ChainLog
from tests.helpers import rewrite_audit_consistently


def make(db: Database, clock: FakeClock) -> ChainService:
    return ChainService(clock, AuditService(clock))


def log_rows(db: Database) -> int:
    with db.read() as session:
        return int(session.scalar(select(func.count()).select_from(ChainLog)) or 0)


def mint(svc: ChainService, session: Any, who: str, amount: int) -> None:
    svc.ensure_token(session, "GBP", 2, "test")
    svc.send(
        session, contract="token:GBP", function="mint", args=[svc.wallet(user_wallet(who)), amount],
        caller=BANK, actor_id="test",
    )  # fmt: skip


def balance(svc: ChainService, db: Database, who: str) -> int:
    with db.read() as session:
        return int(svc.call(session, "token:GBP", "balanceOf", [svc.wallet(user_wallet(who))])[0])


def test_ready_deploys_once_and_says_so_in_the_audit_log(db: Database, clock: FakeClock) -> None:
    svc = make(db, clock)
    for _ in range(2):
        with db.write() as session:
            svc.ready(session)
    with db.read() as session:
        actions = [e.action for e in session.scalars(select(AuditEvent)).all()]
        status = svc.status(session)
    assert actions == ["system.chain_ready"], "one audit event, however often it is called"
    assert status["ready"] and [c["label"] for c in status["contracts"]] == ["escrow", "anchor"]
    assert status["integrity"] == {"ok": True, "problem": None}
    assert log_rows(db) == 2


def test_the_chain_survives_a_restart_with_the_same_addresses_and_balances(
    db: Database, clock: FakeClock
) -> None:
    first = make(db, clock)
    with db.write() as session:
        first.ready(session)
        mint(first, session, "p1", 12_345)
    with db.read() as session:
        a = first.status(session)
    second = make(db, clock)  # a new process: empty memory, same database
    with db.read() as session:
        b = second.status(session)
    assert [c["address"] for c in a["contracts"]] == [c["address"] for c in b["contracts"]]
    assert (a["block"], a["log"]) == (b["block"], b["log"])
    assert balance(second, db, "p1") == 12_345


def test_a_request_that_fails_halfway_leaves_no_trace_on_the_chain(
    db: Database, clock: FakeClock
) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
        mint(svc, session, "p1", 100)
    with pytest.raises(RuntimeError), db.write() as session:
        mint(svc, session, "p1", 900)  # applied to the chain, then the request fails
        raise RuntimeError("the request failed after the chain moved")
    assert log_rows(db) == 4, "the rolled-back transaction is not in the log"
    assert balance(svc, db, "p1") == 100, "and the chain was rebuilt without it"
    with db.write() as session:
        mint(svc, session, "p1", 5)
    assert balance(svc, db, "p1") == 105


def test_a_contract_refusal_writes_nothing(db: Database, clock: FakeClock) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
        svc.ensure_token(session, "GBP", 2, "test")
    rows = log_rows(db)
    with pytest.raises(errors.InvalidState) as caught, db.write() as session:
        svc.send(
            session, contract="token:GBP", function="mint", args=[svc.wallet("user:x"), 1],
            caller="user:x", actor_id="test",
        )  # fmt: skip
    assert caught.value.extra["chain_reason"] == "ONLY_ISSUER"
    assert "different party" in caught.value.detail
    assert log_rows(db) == rows


def test_each_logged_row_covers_the_one_before_it(db: Database, clock: FakeClock) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
        mint(svc, session, "p1", 1)
    with db.read() as session:
        rows = [
            (r.seq, r.prev_hash, r.tx_hash)
            for r in session.scalars(select(ChainLog).order_by(ChainLog.seq))
        ]
    assert [seq for seq, _, _ in rows] == list(range(1, len(rows) + 1))
    assert rows[0][1] == GENESIS
    assert all(b[1] == a[2] for a, b in pairwise(rows))
    assert len({tx for _, _, tx in rows}) == len(rows)


def edit_log(db_path: Path, sql: str, *params: Any) -> None:
    """What a person with direct database access could do: drop the trigger and edit a row."""
    con = sqlite3.connect(db_path)
    con.execute("DROP TRIGGER IF EXISTS chain_log_no_update")
    con.execute(sql, params)
    con.commit()
    con.close()


def test_the_database_refuses_edits_and_deletes_of_the_chain_log(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
    con = sqlite3.connect(db_path)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("UPDATE chain_log SET at = 1 WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        con.execute("DELETE FROM chain_log WHERE seq = 1")
    con.close()


def test_editing_the_log_behind_the_apps_back_is_caught_and_stops_the_chain(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
        mint(svc, session, "p1", 100)
    edit_log(db_path, "UPDATE chain_log SET args_json = ? WHERE seq = 4", '["0x00", 999999999]')
    fresh = make(db, clock)
    with db.read() as session:
        status = fresh.status(session)
    assert status["integrity"]["ok"] is False
    assert "changed after it was written" in status["integrity"]["problem"]
    with pytest.raises(errors.InvalidState) as caught, db.write() as session:
        mint(fresh, session, "p1", 1)
    assert caught.value.extra["chain_reason"] == "LOG_CORRUPT"


def test_sandbox_time_travel_is_logged_and_survives_a_restart(
    db: Database, clock: FakeClock
) -> None:
    svc = make(db, clock)
    with db.write() as session:
        svc.ready(session)
        base = svc.chain_time(session)
        moved = svc.advance(session, seconds=3 * 86_400, actor_id="admin")
    assert moved - base >= 3 * 86_400
    clock.advance(60)
    again = make(db, clock)
    with db.read() as session:
        assert again.status(session)["time_offset_seconds"] == 3 * 86_400
        assert again.chain_time(session) >= moved + 60
    with pytest.raises(errors.ValidationFailed), db.write() as session:
        svc.advance(session, seconds=0, actor_id="admin")


def test_unknown_chain_labels_are_not_usable_before_deploy(db: Database, clock: FakeClock) -> None:
    svc = make(db, clock)
    with db.read() as session:
        assert svc.status(session)["ready"] is False
        assert svc.anchors(session) == []


# --- anchoring the audit log ---------------------------------------------------------------------
def seed_audit(svc: ChainService, db: Database, clock: FakeClock, events: int = 5) -> AuditService:
    audit = AuditService(clock)
    with db.write() as session:
        for i in range(events):
            audit.append(
                session,
                actor_type="system",
                actor_id="system",
                action="test.event",
                detail=f"event {i}",
            )
    return audit


def test_anchoring_writes_the_audit_head_on_the_chain_and_verification_passes(
    db: Database, clock: FakeClock
) -> None:
    svc = make(db, clock)
    seed_audit(svc, db, clock)
    with db.write() as session:
        result = svc.anchor_audit(session, "admin")
    assert result["seq"] == 6 and len(result["head"]) == 64, "5 events, then the chain-ready event"
    with db.read() as session:
        anchors = svc.anchors(session)
        verdict = svc.verify_anchors(session)
        last = session.scalar(select(AuditEvent.action).order_by(AuditEvent.seq.desc()))
    assert [a["seq"] for a in anchors] == [6] and anchors[0]["head"] == result["head"]
    assert verdict["status"] == "PASS" and verdict["anchors"][0]["state"] == "MATCH"
    assert last == "chain.anchored", "anchoring is itself in the audit log"


def test_verify_says_no_anchor_until_something_is_anchored(db: Database, clock: FakeClock) -> None:
    svc = make(db, clock)
    seed_audit(svc, db, clock)
    with db.read() as session:
        assert svc.verify_anchors(session)["status"] == "NO_ANCHOR"


def test_anchoring_again_adds_a_newer_anchor_and_both_still_verify(
    db: Database, clock: FakeClock
) -> None:
    svc = make(db, clock)
    seed_audit(svc, db, clock)
    with db.write() as session:
        first = svc.anchor_audit(session, "admin")
    with db.write() as session:
        second = svc.anchor_audit(session, "admin")  # the first anchoring added an audit event
    assert second["seq"] > first["seq"]
    with db.read() as session:
        verdict = svc.verify_anchors(session)
    assert verdict["status"] == "PASS" and [a["state"] for a in verdict["anchors"]] == [
        "MATCH",
        "MATCH",
    ]


def test_a_rewritten_audit_log_with_recomputed_hashes_passes_the_chain_check_but_not_the_anchor(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    svc = make(db, clock)
    audit = seed_audit(svc, db, clock)
    with db.write() as session:
        svc.anchor_audit(session, "admin")
    rewrite_audit_consistently(db_path, seq=2, detail="event 1, but rewritten")
    with db.read() as session:
        plain = audit.verify(session)
        verdict = svc.verify_anchors(session)
    assert plain.ok, "the hash chain alone cannot see a consistent rewrite"
    assert verdict["status"] == "FAIL"
    assert verdict["anchors"][0]["state"] == "MISMATCH"
    assert verdict["anchors"][0]["database_hash"] != verdict["anchors"][0]["head"]


def test_a_clumsy_edit_fails_both_the_chain_check_and_the_anchor(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    svc = make(db, clock)
    seed_audit(svc, db, clock)
    with db.write() as session:
        svc.anchor_audit(session, "admin")
    con = sqlite3.connect(db_path)
    con.execute("DROP TRIGGER audit_events_no_update")
    con.execute("UPDATE audit_events SET detail = 'edited' WHERE seq = 3")
    con.commit()
    con.close()
    with db.read() as session:
        verdict = svc.verify_anchors(session)
    assert verdict["status"] == "FAIL" and verdict["audit_chain"]["status"] == "FAIL"


def test_cutting_off_the_end_of_the_audit_log_is_caught(
    db: Database, clock: FakeClock, db_path: Path
) -> None:
    svc = make(db, clock)
    seed_audit(svc, db, clock)
    with db.write() as session:
        svc.anchor_audit(session, "admin")
    con = sqlite3.connect(db_path)
    con.execute("DROP TRIGGER audit_events_no_delete")
    con.execute("DELETE FROM audit_events WHERE seq >= 4")
    con.commit()
    con.close()
    with db.read() as session:
        verdict = svc.verify_anchors(session)
    assert verdict["status"] == "FAIL"
    assert verdict["anchors"][0]["state"] == "MISSING_EVENT"


def test_the_escrow_label_and_wallets_are_stable() -> None:
    assert ESCROW == "escrow"
    assert user_wallet("usr_1") == "user:usr_1"
