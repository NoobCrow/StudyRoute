"""Programmable escrow on the sandbox chain, through the API.

Planning is free. Locking funds, paying early and cancelling need MFA for that exact escrow.
The schedule pays itself, the bank's reviewer can freeze (and nothing more), and the AI has no
escrow permission at all.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from app.core.secret_store import _generate_aes_key, _generate_ec_pem, _generate_hex_secret
from app.models import ChainLog
from tests.helpers import World, rewrite_audit_consistently

GBP_10K = {"amount_minor": 1_000_000, "currency": "GBP"}
FIRST_RELEASE = "2026-10-28"  # the fake clock starts on 14 October 2026


def plan(world: World, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "recipient_id": world.recipient_id(),
        "purpose": "TUITION",
        "total": GBP_10K,
        "tranches": 1,
        "first_release": FIRST_RELEASE,
        "cadence": "ONCE",
        "reference": "INV-2026-4471 / STU-883201",
    }
    body.update(overrides)
    who = body.pop("who", "parent")
    response = world.call("POST", "/escrows", who, json=body, idem=True)
    assert response.status_code == 201, response.text
    return dict(response.json())


def fund(world: World, escrow: dict[str, Any]) -> dict[str, Any]:
    world.verify_kyc()
    proof = world.mfa("parent", "confirm_escrow", escrow["escrow_id"])
    response = world.call("POST", f"/escrows/{escrow['escrow_id']}/confirm", idem=True, mfa=proof)
    assert response.status_code == 200, response.text
    return dict(response.json())


def monthly(world: World, tranches: int = 3, total: int = 900_000) -> dict[str, Any]:
    return fund(
        world,
        plan(
            world, purpose="LIVING", total={"amount_minor": total, "currency": "GBP"},
            tranches=tranches, cadence="MONTHLY", reference="Living costs",
        ),
    )  # fmt: skip


def get(world: World, escrow_id: str, who: str = "parent") -> dict[str, Any]:
    response = world.call("GET", f"/escrows/{escrow_id}", who)
    assert response.status_code == 200, response.text
    return dict(response.json())


def states(escrow: dict[str, Any]) -> list[str]:
    return [t["state"] for t in escrow["tranches"]]


def advance(world: World, days: int) -> dict[str, Any]:
    response = world.call("POST", "/chain/sandbox/advance", "admin", json={"days": days})
    assert response.status_code == 200, response.text
    return dict(response.json())


def actions(world: World) -> list[str]:
    """Escrow and chain audit events, oldest first (the rest of the log is not this feature's)."""
    names = [r["action"] for r in reversed(world.audit_rows())]
    return [a for a in names if a.startswith(("escrow.", "chain.", "system.chain"))]


# --- planning ----------------------------------------------------------------------------------
def test_planning_shows_the_schedule_and_locks_nothing(world: World) -> None:
    escrow = plan(
        world,
        purpose="LIVING",
        total={"amount_minor": 1_000_001, "currency": "GBP"},
        tranches=3,
        cadence="MONTHLY",
    )
    assert escrow["status"] == "PENDING_CONFIRMATION" and escrow["chain_status"] is None
    assert [t["amount"]["amount_minor"] for t in escrow["tranches"]] == [333_334, 333_334, 333_333]
    assert [t["release_on"] for t in escrow["tranches"]] == [
        "2026-10-28",
        "2026-11-28",
        "2026-12-28",
    ]
    assert {t["state"] for t in escrow["tranches"]} == {"PLANNED"}
    assert (
        escrow["chain"] is None and len(escrow["plan_hash"]) == 64 and escrow["simulated"] is True
    )
    assert escrow["blockers"][0]["code"] == "KYC_NOT_VERIFIED"
    assert world.call("GET", "/chain/status").json()["ready"] is False, (
        "planning does not touch the chain"
    )
    assert actions(world) == ["escrow.planned"]


@pytest.mark.parametrize(
    ("override", "status"),
    [
        ({"total": {"amount_minor": 1_000_000, "currency": "USD"}}, 422),  # the UK is paid in GBP
        ({"recipient_id": "rcp_does_not_exist"}, 404),
        ({"reference": "bad <script> reference"}, 422),
        ({"first_release": "2026-10-01"}, 422),  # in the past
        ({"first_release": "2031-01-01"}, 422),  # too far ahead
        ({"tranches": 30}, 422),
        (
            {"total": {"amount_minor": 3, "currency": "GBP"}, "tranches": 5},
            422,
        ),  # too small to split
        ({"total": {"amount_minor": 99_999_999, "currency": "GBP"}}, 422),  # over the sandbox cap
        ({"purpose": "GIFT"}, 422),
    ],
)
def test_bad_plans_are_refused(world: World, override: dict[str, Any], status: int) -> None:
    body = {
        "recipient_id": world.recipient_id(), "purpose": "TUITION", "total": GBP_10K, "tranches": 1,
        "first_release": FIRST_RELEASE, "cadence": "ONCE", "reference": "INV-1",
    }  # fmt: skip
    body.update(override)
    response = world.call("POST", "/escrows", json=body, idem=True)
    assert response.status_code == status, response.text


def test_a_plan_needs_an_idempotency_key_and_a_retry_does_not_plan_twice(world: World) -> None:
    body = {
        "recipient_id": world.recipient_id(), "purpose": "TUITION", "total": GBP_10K, "tranches": 1,
        "first_release": FIRST_RELEASE, "cadence": "ONCE", "reference": "INV-1",
    }  # fmt: skip
    assert world.call("POST", "/escrows", json=body).status_code == 400
    key = str(uuid.uuid4())
    first = world.call("POST", "/escrows", json=body, idem=key)
    again = world.call("POST", "/escrows", json=body, idem=key)
    assert again.headers.get("Idempotent-Replay") == "true"
    assert first.json()["escrow_id"] == again.json()["escrow_id"]
    assert len(world.call("GET", "/escrows").json()["items"]) == 1


def test_a_beneficiary_that_matches_the_screening_list_is_blocked_and_audited(world: World) -> None:
    world.call("PUT", "/config/rules", "admin", json={
        "key": "compliance.sanctions_test_token", "value": "University of Example",
        "reason": "demo of a config-driven screening list",
    })  # fmt: skip
    body = {
        "recipient_id": world.recipient_id(), "purpose": "TUITION", "total": GBP_10K, "tranches": 1,
        "first_release": FIRST_RELEASE, "cadence": "ONCE", "reference": "INV-1",
    }  # fmt: skip
    response = world.call("POST", "/escrows", json=body, idem=True)
    assert response.status_code == 422 and response.json()["code"] == "SANCTIONS_HIT"
    blocked = world.audit_rows(action="escrow.blocked")
    assert len(blocked) == 1 and blocked[0]["decision"] == "blocked"
    assert world.call("GET", "/escrows").json()["items"] == [], "no plan was stored"


# --- who may do what ---------------------------------------------------------------------------
def test_the_ai_has_no_escrow_or_chain_permission_at_all(world: World) -> None:
    ai = world.ai_headers()
    for method, path in (
        ("GET", "/escrows"), ("GET", "/chain/status"), ("GET", "/chain/anchors"),
        ("POST", "/escrows"), ("POST", "/chain/anchor"), ("GET", "/chain/verify"),
    ):  # fmt: skip
        reply = world.client.request(
            method, f"/api/v1{path}", headers=ai, json={} if method == "POST" else None
        )
        assert reply.status_code == 403, (method, path)


def test_a_student_can_look_but_not_plan_and_the_reviewer_cannot_plan_either(world: World) -> None:
    escrow = monthly(world)
    assert [e["escrow_id"] for e in world.call("GET", "/escrows", "student").json()["items"]] == [
        escrow["escrow_id"]
    ]
    assert get(world, escrow["escrow_id"], "student")["chain_status"] == "ACTIVE"
    body = {
        "recipient_id": world.recipient_id(),
        "total": GBP_10K,
        "first_release": FIRST_RELEASE,
        "reference": "x1",
    }
    assert world.call("POST", "/escrows", "student", json=body, idem=True).status_code == 403
    assert world.call("POST", "/escrows", "admin", json=body, idem=True).status_code == 403
    assert len(world.call("GET", "/escrows", "admin").json()["items"]) == 1, (
        "a reviewer sees every escrow"
    )


def test_only_the_parent_can_confirm_release_or_cancel(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    for who in ("student", "admin"):
        assert world.call("POST", f"/escrows/{eid}/cancel", who, idem=True).status_code == 403
        assert (
            world.call("POST", f"/escrows/{eid}/tranches/0/release", who, idem=True).status_code
            == 403
        )


# --- locking funds ------------------------------------------------------------------------------
def test_confirming_needs_mfa_for_this_exact_escrow(world: World) -> None:
    world.verify_kyc()
    first, other = plan(world), plan(world, reference="INV-2")
    path = f"/escrows/{first['escrow_id']}/confirm"
    assert world.call("POST", path, idem=True).status_code == 403
    wrong_subject = world.mfa("parent", "confirm_escrow", other["escrow_id"])
    reply = world.call("POST", path, idem=True, mfa=wrong_subject)
    assert reply.status_code == 403 and reply.json()["code"] == "MFA_REQUIRED"
    wrong_scope = world.mfa("parent", "approve_payment", world.draft()["payment_id"])
    assert world.call("POST", path, idem=True, mfa=wrong_scope).status_code == 403
    bad_code = world.client.post(
        "/api/v1/auth/mfa/verify", headers=world.login("parent"),
        json={"code": "000000", "scope": "confirm_escrow", "subject_id": first["escrow_id"]},
    )  # fmt: skip
    assert bad_code.status_code == 403
    assert world.call("GET", "/chain/status").json()["ready"] is False, "nothing was locked"


def test_confirming_needs_kyc_to_be_verified(world: World) -> None:
    escrow = plan(world)
    proof = world.mfa("parent", "confirm_escrow", escrow["escrow_id"])
    reply = world.call("POST", f"/escrows/{escrow['escrow_id']}/confirm", idem=True, mfa=proof)
    assert reply.status_code == 422 and reply.json()["code"] == "KYC_NOT_VERIFIED"


def test_confirming_locks_the_funds_on_the_chain_and_writes_one_audit_event(world: World) -> None:
    escrow = monthly(world)
    assert escrow["status"] == "ON_CHAIN" and escrow["chain_status"] == "ACTIVE"
    chain = escrow["chain"]
    assert chain["escrow_id"] == 1 and chain["locked"]["amount_minor"] == 900_000
    assert (
        chain["contract"].startswith("0x") and chain["payer_wallet"] != chain["beneficiary_wallet"]
    )
    assert states(escrow) == ["LOCKED"] * 3
    assert [t["function"] for t in escrow["transactions"]] == ["mint", "approve", "create"]
    assert all(len(t["tx_hash"]) == 64 for t in escrow["transactions"])
    assert actions(world) == [
        "escrow.planned",
        "system.chain_ready",
        "escrow.funded",
    ], "three chain transactions, but ONE audit event for the one state change"
    status = world.call("GET", "/chain/status", "student").json()
    assert status["ready"] and status["integrity"]["ok"]
    assert {c["label"] for c in status["contracts"]} == {"escrow", "anchor", "token:GBP"}
    assert world.call("GET", "/audit/verify", "admin").json()["status"] == "PASS"


def test_the_chain_carries_no_personal_data(world: World) -> None:
    escrow = monthly(world)
    shown = str(get(world, escrow["escrow_id"])["transactions"]) + str(escrow["chain"])
    with world.ctx.db.read() as session:
        stored = str([r.args_json for r in session.scalars(select(ChainLog))])
    for text in (shown, stored):
        assert "Living costs" not in text, "the payment reference is hashed, not written"
        assert "University" not in text and "EXMP" not in text, "no name, IBAN or BIC"


def test_an_mfa_proof_works_once_and_a_replayed_confirm_does_not_lock_twice(world: World) -> None:
    world.verify_kyc()
    escrow = plan(world)
    eid = escrow["escrow_id"]
    proof = world.mfa("parent", "confirm_escrow", eid)
    key = str(uuid.uuid4())
    first = world.call("POST", f"/escrows/{eid}/confirm", idem=key, mfa=proof)
    replay = world.call("POST", f"/escrows/{eid}/confirm", idem=key, mfa=proof)
    assert first.status_code == 200 and replay.headers.get("Idempotent-Replay") == "true"
    new_key = world.call("POST", f"/escrows/{eid}/confirm", idem=True, mfa=proof)
    assert new_key.status_code == 409, "the plan is already confirmed"
    assert get(world, eid)["chain"]["escrow_id"] == 1
    assert actions(world).count("escrow.funded") == 1


def test_a_plan_can_be_dropped_before_confirmation_but_not_after(world: World) -> None:
    escrow = plan(world)
    dropped = world.call("POST", f"/escrows/{escrow['escrow_id']}/abandon", idem=True)
    assert dropped.status_code == 200 and dropped.json()["status"] == "ABANDONED"
    assert "escrow.abandoned" in actions(world)
    funded = monthly(world)
    assert (
        world.call("POST", f"/escrows/{funded['escrow_id']}/abandon", idem=True).status_code == 409
    )
    world.verify_kyc()
    proof = world.mfa("parent", "confirm_escrow", escrow["escrow_id"])
    assert (
        world.call(
            "POST", f"/escrows/{escrow['escrow_id']}/confirm", idem=True, mfa=proof
        ).status_code
        == 409
    )


# --- the schedule pays itself -----------------------------------------------------------------------
def test_tranches_are_paid_on_their_dates_without_anyone_asking(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    assert advance(world, 10)["released"] == 0, "26 October: nothing is due yet"
    assert states(get(world, eid)) == ["LOCKED"] * 3
    assert advance(world, 5)["released"] == 1, "31 October: the first tranche is due"
    view = get(world, eid)
    assert states(view) == ["RELEASED", "LOCKED", "LOCKED"]
    assert view["chain"]["locked"]["amount_minor"] == 600_000
    assert advance(world, 60)["released"] == 2
    final = get(world, eid)
    assert states(final) == ["RELEASED"] * 3 and final["chain_status"] == "COMPLETED"
    scheduled = [
        r
        for r in world.audit_rows(action="escrow.tranche_released")
        if r["reason_code"] == "SCHEDULED"
    ]
    assert len(scheduled) == 3 and all(r["actor_type"] == "system" for r in scheduled)
    assert world.call("GET", "/audit/verify", "admin").json()["status"] == "PASS"


def test_paying_early_needs_mfa_and_pays_just_that_tranche(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    path = f"/escrows/{eid}/tranches/2/release"
    assert world.call("POST", path, idem=True).status_code == 403
    assert (
        world.call(
            "POST",
            f"/escrows/{eid}/tranches/9/release",
            idem=True,
            mfa=world.mfa("parent", "release_escrow", eid),
        ).status_code
        == 404
    )
    proof = world.mfa("parent", "release_escrow", eid)
    reply = world.call("POST", path, idem=True, mfa=proof)
    assert reply.status_code == 200, reply.text
    assert states(reply.json()) == ["LOCKED", "LOCKED", "RELEASED"]
    early = world.audit_rows(action="escrow.tranche_released")[0]
    assert early["reason_code"].startswith("mfa:") and early["amount_minor"] == 300_000
    again = world.call("POST", path, idem=True, mfa=world.mfa("parent", "release_escrow", eid))
    assert again.status_code == 409, "a tranche pays once"
    assert (
        world.call("POST", f"/escrows/{eid}/tranches/1/release", idem=True, mfa=proof).status_code
        == 403
    ), "one proof, one use"


def test_cancelling_takes_back_only_what_is_not_yet_due(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    advance(world, 15)  # the first tranche is paid by the schedule
    assert world.call("POST", f"/escrows/{eid}/cancel", idem=True).status_code == 403, (
        "cancelling needs MFA"
    )
    reply = world.call(
        "POST", f"/escrows/{eid}/cancel", idem=True, mfa=world.mfa("parent", "cancel_escrow", eid)
    )
    assert reply.status_code == 200, reply.text
    view = reply.json()
    assert (
        states(view) == ["RELEASED", "REFUNDED", "REFUNDED"] and view["chain_status"] == "CANCELLED"
    )
    cancelled = world.audit_rows(action="escrow.cancelled")[0]
    assert cancelled["amount_minor"] == 600_000 and cancelled["reason_code"].startswith("mfa:")
    assert (
        world.call(
            "POST",
            f"/escrows/{eid}/cancel",
            idem=True,
            mfa=world.mfa("parent", "cancel_escrow", eid),
        ).status_code
        == 409
    )


def test_a_refused_visa_the_university_sends_a_tranche_back(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    assert (
        world.call("POST", f"/escrows/{eid}/tranches/0/sandbox-refund", "parent").status_code == 403
    )
    reply = world.call("POST", f"/escrows/{eid}/tranches/0/sandbox-refund", "admin")
    assert reply.status_code == 200 and states(reply.json()) == ["REFUNDED", "LOCKED", "LOCKED"]
    assert "escrow.tranche_returned" in actions(world)


# --- compliance ------------------------------------------------------------------------------------
def test_a_frozen_escrow_moves_nothing_until_the_reviewer_unfreezes_it(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    assert (
        world.call(
            "POST", f"/escrows/{eid}/freeze", "parent", json={"reason": "not mine to do"}
        ).status_code
        == 403
    )
    assert (
        world.call("POST", f"/escrows/{eid}/freeze", "admin", json={"reason": "no"}).status_code
        == 422
    )
    frozen = world.call(
        "POST",
        f"/escrows/{eid}/freeze",
        "admin",
        json={"reason": "Sanctions screening hit, under review"},
    )
    assert frozen.status_code == 200 and frozen.json()["chain_status"] == "FROZEN"
    event = world.audit_rows(action="escrow.frozen")[0]
    assert event["decision"] == "blocked" and event["reason_code"] == "COMPLIANCE_HOLD"
    assert "Sanctions screening hit" in event["detail"]
    assert advance(world, 60)["released"] == 0, "the date came and went; the freeze held"
    assert states(get(world, eid)) == ["LOCKED"] * 3
    early = world.call(
        "POST",
        f"/escrows/{eid}/tranches/0/release",
        idem=True,
        mfa=world.mfa("parent", "release_escrow", eid),
    )
    assert early.status_code == 409 and early.json()["chain_reason"] == "NOT_ACTIVE"
    cancel = world.call(
        "POST", f"/escrows/{eid}/cancel", idem=True, mfa=world.mfa("parent", "cancel_escrow", eid)
    )
    assert cancel.status_code == 409
    freeze_again = world.call(
        "POST", f"/escrows/{eid}/freeze", "admin", json={"reason": "again please"}
    )
    assert freeze_again.status_code == 409
    thawed = world.call(
        "POST", f"/escrows/{eid}/unfreeze", "admin", json={"reason": "Cleared after review"}
    )
    assert thawed.status_code == 200 and thawed.json()["chain_status"] == "ACTIVE"
    assert world.ctx.escrow.advance_due(world.ctx.db) == 2, "both overdue tranches are now paid"
    assert "escrow.unfrozen" in actions(world)


# --- the chain survives ------------------------------------------------------------------------------
def test_the_chain_is_rebuilt_from_the_log_after_a_restart(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    advance(world, 15)
    before = get(world, eid)
    world.ctx.chain._chain = None  # a new process: the EVM is empty, the database is not
    after = get(world, eid)
    assert states(after) == states(before) == ["RELEASED", "LOCKED", "LOCKED"]
    assert after["chain"]["contract"] == before["chain"]["contract"]
    assert after["chain"]["locked"] == before["chain"]["locked"]
    status = world.call("GET", "/chain/status").json()
    assert status["time_offset_seconds"] == 15 * 86_400 and status["integrity"]["ok"]


def test_a_request_that_fails_after_the_chain_moved_leaves_no_trace(world: World) -> None:
    escrow = monthly(world)
    eid = escrow["escrow_id"]
    before = get(world, eid)
    good = world.mfa("parent", "release_escrow", eid)
    # make the audit write fail AFTER the chain has paid, so the whole request rolls back
    original = world.ctx.audit.append

    def broken(*args: Any, **kwargs: Any) -> Any:
        if kwargs.get("action") == "escrow.tranche_released":
            raise RuntimeError("audit store unavailable")
        return original(*args, **kwargs)

    world.ctx.audit.append = broken  # type: ignore[method-assign]
    try:
        try:
            reply = world.call("POST", f"/escrows/{eid}/tranches/0/release", idem=True, mfa=good)
            assert reply.status_code == 500
        except RuntimeError:
            pass  # the test client re-raises server errors
    finally:
        world.ctx.audit.append = original  # type: ignore[method-assign]
    after = get(world, eid)
    assert states(after) == states(before) == ["LOCKED"] * 3, (
        "the chain was rebuilt without the lost payment"
    )
    assert world.call("GET", "/audit/verify", "admin").json()["status"] == "PASS"


# --- anchoring the audit log on the chain --------------------------------------------------------------
def test_the_reviewer_anchors_the_audit_log_and_anyone_can_see_it(world: World) -> None:
    monthly(world)
    assert world.call("POST", "/chain/anchor", "parent").status_code == 403
    reply = world.call("POST", "/chain/anchor", "admin")
    assert reply.status_code == 201 and reply.json()["simulated"] is True
    anchors = world.call("GET", "/chain/anchors", "student").json()["items"]
    assert [a["seq"] for a in anchors] == [reply.json()["seq"]]
    assert world.call("GET", "/chain/verify", "student").status_code == 403, (
        "verifying is for the reviewer"
    )
    verdict = world.call("GET", "/chain/verify", "admin").json()
    assert verdict["status"] == "PASS" and verdict["anchors"][0]["state"] == "MATCH"
    assert "chain.anchored" in actions(world)


def test_a_tampered_audit_log_is_caught_by_the_anchor_even_if_the_hashes_are_recomputed(
    world: World, tmp_path: Path
) -> None:
    monthly(world)
    world.call("POST", "/chain/anchor", "admin")
    seq = world.audit_rows(action="escrow.funded")[0]["seq"]
    rewrite_audit_consistently(tmp_path / "test.db", seq, "Nothing to see here")
    assert world.call("GET", "/audit/verify", "admin").json()["status"] == "PASS", (
        "the hash chain alone is fooled"
    )
    verdict = world.call("GET", "/chain/verify", "admin").json()
    assert verdict["status"] == "FAIL" and verdict["anchors"][0]["state"] == "MISMATCH"


def test_verification_says_so_when_nothing_is_anchored(world: World) -> None:
    assert world.call("GET", "/chain/verify", "admin").json()["status"] == "NO_ANCHOR"


# --- the sandbox boundary ------------------------------------------------------------------------------
def test_production_mode_has_no_escrow_or_chain_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", _generate_ec_pem().replace("\n", chr(92) + "n"))
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", _generate_aes_key())
    for provider in ("PROV_A", "PROV_B", "PROV_C"):
        monkeypatch.setenv(f"WEBHOOK_SECRET_{provider}", _generate_hex_secret())
    prod = World(tmp_path, app_env="production")
    try:
        for path in ("/escrows", "/chain/status", "/chain/anchors", "/chain/verify"):
            assert prod.client.get(f"/api/v1{path}").status_code == 404, path
    finally:
        prod.close()
