"""A thief or a man in the middle on plain HTTP who holds a captured bearer token.

Reading what is sent is not defended without TLS (risk R4). What must hold is that a captured token
alone moves no money: approving and allowlisting need a fresh MFA proof, a payment to a recipient the
thief added cannot be put up for approval, and replaying a recorded approval makes no second approval.
An in-process version of scripts/security/mitm_probe.py.
"""

from __future__ import annotations

import uuid

from tests.helpers import World


def approvals(world: World, payment_id: str) -> int:
    timeline = world.call("GET", f"/payments/{payment_id}/tracker").json()["timeline"]
    return sum(1 for step in timeline if step["state"] == "APPROVED")


def test_a_captured_token_alone_cannot_approve_a_payment(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    thief = world.call(
        "POST",
        f"/payments/{pid}/approve",
        json={"confirm_summary_hash": approval["summary_hash"]},
        idem=True,
    )
    assert thief.status_code == 403 and thief.json()["code"] == "MFA_REQUIRED"
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "PENDING_APPROVAL"


def test_a_captured_token_alone_cannot_allowlist_or_delist_a_recipient(world: World) -> None:
    world.verify_kyc()
    rid = world.recipient_id()
    delist = world.call("PATCH", f"/recipients/{rid}", json={"allowlisted": False})
    allow = world.call("PATCH", f"/recipients/{rid}", json={"allowlisted": True})
    assert delist.status_code == 403 and allow.status_code == 403


def test_a_payment_to_a_recipient_the_thief_added_cannot_be_put_up_for_approval(
    world: World,
) -> None:
    world.verify_kyc()
    added = world.call(
        "POST",
        "/recipients",
        json={
            "type": "UNIVERSITY",
            "display_name": "Attacker Account",
            "country": "GB",
            "bic": "EXMPGB2L",
            "iban": "GB29NWBK60161331926819",
        },
    )
    assert added.status_code == 201, added.text
    draft = world.draft(recipient_id=added.json()["recipient_id"], reference="ATTACKER")
    asked = world.call("POST", f"/payments/{draft['payment_id']}/request-approval", idem=True)
    assert asked.status_code == 422
    assert asked.json()["code"] == "RECIPIENT_NOT_ALLOWLISTED"
    assert (
        world.call("GET", f"/payments/{draft['payment_id']}").json()["state"] != "PENDING_APPROVAL"
    )


def test_replaying_a_recorded_approval_makes_only_one_approval(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    proof = world.mfa("parent", "approve_payment", pid)
    key = str(uuid.uuid4())
    first = world.approve(approval, mfa=proof, idem=key)
    assert first.status_code == 200
    assert approvals(world, pid) == 1

    same_key = world.approve(approval, mfa=proof, idem=key)  # the recorded request, sent again
    assert same_key.status_code == 200 and same_key.json() == first.json()
    assert approvals(world, pid) == 1

    new_key = world.approve(approval, mfa=proof, idem=str(uuid.uuid4()))  # same proof, new key
    assert new_key.status_code >= 400
    assert approvals(world, pid) == 1
