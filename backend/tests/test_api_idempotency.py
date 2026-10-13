"""Idempotency keys (T04, T05) and optimistic locking against double approval."""

from __future__ import annotations

import threading
import uuid

from tests.helpers import World


def test_T04_same_key_same_request_approves_exactly_once(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    proof = world.mfa("parent", "approve_payment", pid)
    key = str(uuid.uuid4())

    first = world.approve(approval, idem=key, mfa=proof)
    second = world.approve(approval, idem=key, mfa=proof)

    assert first.status_code == second.status_code == 200
    assert "idempotent-replay" not in first.headers
    assert second.headers["idempotent-replay"] == "true"
    assert first.json() == second.json()
    assert len(world.audit_rows(action="approval.granted", payment_id=pid)) == 1
    states = [r["detail"] for r in world.audit_rows(payment_id=pid) if "via approve" in str(r["detail"])]
    assert len(states) == 1


def test_a_second_approve_with_a_new_key_is_a_conflict_not_a_second_approval(world: World) -> None:
    approval = world.ready_payment()
    assert world.approve(approval).status_code == 200
    again = world.approve(approval)
    assert again.status_code == 409
    assert again.json()["code"] == "INVALID_STATE"
    assert len(world.audit_rows(action="approval.granted", payment_id=approval["payment_id"])) == 1


def test_T05_same_key_with_a_different_body_is_refused(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    key = str(uuid.uuid4())
    first = world.call(
        "POST", f"/payments/{pid}/approve", json={"confirm_summary_hash": "sha256:" + "a" * 64},
        idem=key, mfa=world.mfa("parent", "approve_payment", pid),
    )  # fmt: skip
    assert first.status_code == 409  # wrong summary hash is refused, but that reply is replayable
    other = world.call(
        "POST", f"/payments/{pid}/approve", json={"confirm_summary_hash": approval["summary_hash"]},
        idem=key, mfa=world.mfa("parent", "approve_payment", pid),
    )  # fmt: skip
    assert other.status_code == 422
    assert other.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_T05_creating_a_payment_twice_with_one_key_but_different_bodies(world: World) -> None:
    quote = world.quote()
    key = str(uuid.uuid4())
    body = {
        "quote_id": quote["quote_id"], "provider_id": "prov_b",
        "recipient_id": world.recipient_id(), "reference": "INV-1",
    }  # fmt: skip
    assert world.call("POST", "/payments", json=body, idem=key).status_code == 201
    changed = {**body, "reference": "INV-2"}
    response = world.call("POST", "/payments", json=changed, idem=key)
    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_replaying_a_create_returns_the_same_payment_not_a_second_one(world: World) -> None:
    quote = world.quote()
    key = str(uuid.uuid4())
    body = {
        "quote_id": quote["quote_id"], "provider_id": "prov_b",
        "recipient_id": world.recipient_id(), "reference": "INV-1",
    }  # fmt: skip
    first = world.call("POST", "/payments", json=body, idem=key)
    second = world.call("POST", "/payments", json=body, idem=key)
    assert second.headers["idempotent-replay"] == "true"
    assert first.json()["payment_id"] == second.json()["payment_id"]
    assert len(world.call("GET", "/payments").json()["items"]) == 1


def test_idempotency_key_is_required_and_must_be_a_uuid(world: World) -> None:
    quote = world.quote()
    body = {
        "quote_id": quote["quote_id"], "provider_id": "prov_b",
        "recipient_id": world.recipient_id(), "reference": "INV-1",
    }  # fmt: skip
    missing = world.call("POST", "/payments", json=body)
    assert missing.status_code == 400 and missing.json()["code"] == "BAD_REQUEST"
    malformed = world.call("POST", "/payments", json=body, idem="not-a-uuid")
    assert malformed.status_code == 400


def test_keys_are_scoped_to_the_user(world: World) -> None:
    key = str(uuid.uuid4())
    quote = world.quote()
    body = {
        "quote_id": quote["quote_id"], "provider_id": "prov_b",
        "recipient_id": world.recipient_id(), "reference": "INV-1",
    }  # fmt: skip
    assert world.call("POST", "/payments", json=body, idem=key).status_code == 201
    # a student cannot create drafts at all, and the parent's key means nothing to them
    assert world.call("POST", "/payments", "student", json=body, idem=key).status_code == 403


def test_two_simultaneous_approvals_cannot_both_succeed(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    proofs = [world.mfa("parent", "approve_payment", pid) for _ in range(2)]
    headers = world.login("parent")
    results: list[int] = []

    def attempt(proof: str) -> None:
        response = world.client.post(
            f"/api/v1/payments/{pid}/approve",
            headers={**headers, "Idempotency-Key": str(uuid.uuid4()), "X-MFA-Proof": proof},
            json={"confirm_summary_hash": approval["summary_hash"]},
        )
        results.append(response.status_code)

    threads = [threading.Thread(target=attempt, args=(p,)) for p in proofs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 409]
    assert len(world.audit_rows(action="approval.granted", payment_id=pid)) == 1
