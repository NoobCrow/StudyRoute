"""MFA proofs (T08), summary-hash binding, illegal transitions (T15), cancel and reject."""

from __future__ import annotations

import pytest

from app.core import errors
from app.domain.rules import load_rules
from tests.helpers import World


def test_T08_approve_without_an_mfa_proof_is_403_mfa_required(world: World) -> None:
    approval = world.ready_payment()
    response = world.call(
        "POST", f"/payments/{approval['payment_id']}/approve",
        json={"confirm_summary_hash": approval["summary_hash"]}, idem=True,
    )  # fmt: skip
    assert response.status_code == 403
    assert response.json()["code"] == "MFA_REQUIRED"
    assert world.audit_rows(action="approval.blocked", reason_code="MFA_REQUIRED")


def _extend_quote_validity(world: World) -> None:
    world.call("PUT", "/config/rules", "admin", json={
        "key": "engine.quote_ttl_seconds", "value": 3600, "verified": True, "reason": "long quote",
    })  # fmt: skip


def test_T08_a_proof_still_works_just_inside_five_minutes(world: World) -> None:
    _extend_quote_validity(world)
    approval = world.ready_payment()
    proof = world.mfa("parent", "approve_payment", approval["payment_id"])
    world.clock.advance(299)
    assert world.approve(approval, mfa=proof).status_code == 200


def test_T08_a_proof_older_than_five_minutes_is_403_mfa_required(world: World) -> None:
    _extend_quote_validity(world)
    approval = world.ready_payment()
    proof = world.mfa("parent", "approve_payment", approval["payment_id"])
    world.clock.advance(301)
    response = world.approve(approval, mfa=proof)
    assert response.status_code == 403
    assert response.json()["code"] == "MFA_REQUIRED"
    renewed = world.mfa("parent", "approve_payment", approval["payment_id"])
    assert world.approve(approval, mfa=renewed).status_code == 200


def test_a_wrong_mfa_code_is_refused_and_repeated_failures_lock_the_step(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    body = {"code": "000000", "scope": "approve_payment", "subject_id": pid}
    for _ in range(5):
        response = world.call("POST", "/auth/mfa/verify", json=body)
        assert response.status_code == 403
    locked = world.call("POST", "/auth/mfa/verify", json={**body, "code": "246810"})
    assert locked.status_code == 429
    assert "retry-after" in locked.headers


def test_a_proof_is_single_use_and_bound_to_its_payment_and_action(world: World) -> None:
    first = world.ready_payment()
    proof = world.mfa("parent", "approve_payment", first["payment_id"])
    assert world.approve(first, mfa=proof).status_code == 200
    second_quote = world.quote()
    second = world.draft(second_quote, reference="INV-2")
    approval = world.call(
        "POST", f"/payments/{second['payment_id']}/request-approval", idem=True
    ).json()
    assert world.approve(approval, mfa=proof).status_code == 403
    wrong_scope = world.mfa("parent", "allowlist_recipient", world.recipient_id())
    assert world.approve(approval, mfa=wrong_scope).status_code == 403


def test_a_changed_summary_hash_is_refused(world: World) -> None:
    approval = world.ready_payment()
    response = world.approve({**approval, "summary_hash": "sha256:" + "0" * 64})
    assert response.status_code == 409
    assert response.json()["code"] == "SUMMARY_MISMATCH"


def test_editing_the_recipient_after_the_summary_was_shown_invalidates_approval(
    world: World,
) -> None:
    approval = world.ready_payment()
    rid = world.recipient_id()
    proof = world.mfa("parent", "allowlist_recipient", rid)
    renamed = world.call(
        "PATCH", f"/recipients/{rid}", mfa=proof,
        json={"display_name": "Different Name", "allowlisted": True},
    )  # fmt: skip
    assert renamed.status_code == 200
    response = world.approve(approval)
    assert response.status_code == 409
    assert response.json()["code"] == "SUMMARY_MISMATCH"


def test_T15_illegal_transitions_are_409_invalid_state(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    assert world.approve(approval).status_code == 200
    cancel = world.call("POST", f"/payments/{pid}/cancel", idem=True)
    assert cancel.status_code == 200
    assert cancel.json()["state"] == "CANCELLED"
    for path in ("cancel", "request-approval"):
        response = world.call("POST", f"/payments/{pid}/{path}", idem=True)
        assert response.status_code == 409, path
        assert response.json()["code"] == "INVALID_STATE"
    reject = world.call("POST", f"/payments/{pid}/reject", "admin", json={}, idem=True)
    assert reject.status_code == 409


def test_T15_settled_cannot_go_back_to_submitted(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    world.approve(approval)
    world.clock.advance(4)
    world.ctx.worker.tick()
    world.clock.advance(6)
    world.ctx.worker.tick()
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "SETTLED"
    with pytest.raises(errors.InvalidState), world.ctx.db.write() as session:
        world.ctx.payments.submit(session, load_rules(session), pid)


def test_a_draft_cannot_be_approved_and_a_quoted_payment_cannot_skip_ahead(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    payment = world.draft()
    pid = payment["payment_id"]
    body = {"confirm_summary_hash": "sha256:" + "1" * 64}
    proof = world.mfa("parent", "approve_payment", pid)
    response = world.call("POST", f"/payments/{pid}/approve", json=body, idem=True, mfa=proof)
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


def test_admin_can_reject_and_a_parent_can_discard_a_draft(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    rejected = world.call(
        "POST", f"/payments/{pid}/reject", "admin", json={"reason": "demo"}, idem=True
    )
    assert rejected.status_code == 200
    assert rejected.json()["state"] == "REJECTED"
    other = world.draft()
    discard = world.call("POST", f"/payments/{other['payment_id']}/cancel", idem=True)
    assert discard.json()["state"] == "CANCELLED"
