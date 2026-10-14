"""Mock sanctions screening (T17), sandbox caps (T18) and the KYC gate."""

from __future__ import annotations

import json

from tests.helpers import World

SANCTIONED = {
    "type": "UNIVERSITY",
    "display_name": "SANCTION_TEST Trading Ltd",
    "country": "GB",
    "bic": "EXMPGB2L",
    "iban": "GB08EXMP12345612344821",
}


def test_T17_a_sanctions_test_name_is_blocked_with_a_clear_message_and_an_audit_event(
    world: World,
) -> None:
    response = world.call("POST", "/recipients", json=SANCTIONED)
    assert response.status_code == 422
    assert response.json()["code"] == "SANCTIONS_HIT"
    assert "sanctions" in response.json()["detail"].lower()
    rows = world.audit_rows(action="compliance.blocked")
    assert len(rows) == 1
    assert rows[0]["decision"] == "blocked"
    assert rows[0]["reason_code"] == "SANCTIONS_HIT"
    assert "SANCTION_TEST" not in json.dumps(rows)
    names = [r["display_name"] for r in world.call("GET", "/recipients").json()["items"]]
    assert all("SANCTION_TEST" not in name for name in names)


def test_renaming_a_recipient_to_a_sanctioned_name_is_blocked(world: World) -> None:
    rid = world.recipient_id()
    proof = world.mfa("parent", "allowlist_recipient", rid)
    response = world.call(
        "PATCH", f"/recipients/{rid}", mfa=proof, json={"display_name": "SANCTION_TEST Ltd"}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SANCTIONS_HIT"


def test_the_payment_guard_rechecks_sanctions_when_the_config_changes(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    payment = world.draft()
    world.call("PUT", "/config/rules", "admin", json={
        "key": "compliance.sanctions_test_token", "value": "University of Example",
        "reason": "demo of a config-driven screening list",
    })  # fmt: skip
    response = world.call("POST", f"/payments/{payment['payment_id']}/request-approval", idem=True)
    assert response.status_code == 422
    assert response.json()["code"] == "SANCTIONS_HIT"
    assert world.audit_rows(action="compliance.blocked", payment_id=payment["payment_id"])


def draft_and_request(world: World, amount_minor: int):
    quote = world.quote(target={"amount_minor": amount_minor, "currency": "GBP"})
    payment = world.draft(quote, reference=f"INV-{amount_minor}")
    path = f"/payments/{payment['payment_id']}/request-approval"
    return world.call("POST", path, idem=True)


def test_T18_amount_above_the_daily_cap_is_limit_exceeded(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    # GBP 30,000 is about USD 39,344 at the synthetic rates: two fit under the USD 100,000 cap
    assert draft_and_request(world, 3_000_000).status_code == 200
    assert draft_and_request(world, 3_000_000).status_code == 200
    third = draft_and_request(world, 3_000_000)
    assert third.status_code == 422
    assert third.json()["code"] == "LIMIT_EXCEEDED"
    assert third.json()["limit"] == "DAILY_CAP"
    assert "Confirm with your AD bank" in third.json()["detail"]
    rows = world.audit_rows(action="compliance.blocked", reason_code="DAILY_CAP")
    assert len(rows) == 1 and rows[0]["decision"] == "blocked"


def test_a_single_payment_above_the_per_transaction_cap_is_refused(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    response = draft_and_request(world, 5_000_000)  # GBP 50,000 is about USD 65,574
    assert response.status_code == 422
    assert response.json()["limit"] == "PER_TRANSACTION_CAP"


def test_limits_come_from_config_and_the_daily_cap_resets_each_dhaka_day(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    assert draft_and_request(world, 3_000_000).status_code == 200
    assert draft_and_request(world, 3_000_000).status_code == 200
    assert draft_and_request(world, 3_000_000).status_code == 422
    world.clock.advance(24 * 3600)
    assert draft_and_request(world, 3_000_000).status_code == 200


def test_cancelling_a_payment_frees_its_daily_allowance(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    first = draft_and_request(world, 3_000_000).json()
    draft_and_request(world, 3_000_000)
    assert draft_and_request(world, 3_000_000).status_code == 422
    cancel = world.call("POST", f"/payments/{first['payment_id']}/cancel", idem=True)
    assert cancel.status_code == 200
    assert draft_and_request(world, 3_000_000).status_code == 200


def test_kyc_moves_from_needs_documents_to_pending_to_verified(world: World) -> None:
    status = world.call("GET", "/kyc/status").json()
    assert status["status"] == "NEEDS_DOCUMENTS"
    assert status["simulated"] is True
    partial = world.call("POST", "/kyc/mock-submit", json={"documents": ["passport"]}).json()
    assert partial["status"] == "NEEDS_DOCUMENTS"
    assert partial["missing"] == ["parent_id", "source_of_funds"]
    full = ["passport", "parent_id", "source_of_funds"]
    pending = world.call("POST", "/kyc/mock-submit", json={"documents": full}).json()
    assert pending["status"] == "PENDING"
    assert "being reviewed (simulated)" in pending["message"]
    world.clock.advance(7)
    world.ctx.worker.tick()
    assert world.call("GET", "/kyc/status").json()["status"] == "PENDING"
    world.clock.advance(2)
    world.ctx.worker.tick()
    assert world.call("GET", "/kyc/status").json()["status"] == "VERIFIED"
    changed = world.audit_rows(action="kyc.status_changed", actor_type="system")
    assert changed and changed[0]["reason_code"] == "SIMULATED_REVIEW"


def test_the_student_sees_the_parents_kyc_but_only_an_admin_can_review(world: World) -> None:
    assert world.call("GET", "/kyc/status", "student").json()["status"] == "NEEDS_DOCUMENTS"
    review = {"user_id": world.ids["parent"], "status": "VERIFIED"}
    assert world.call("PUT", "/kyc/mock-review", "student", json=review).status_code == 403
    assert world.call("PUT", "/kyc/mock-review", "parent", json=review).status_code == 403
    assert world.call("PUT", "/kyc/mock-review", "admin", json=review).status_code == 200
    assert world.call("GET", "/kyc/status", "student").json()["status"] == "VERIFIED"


def test_an_admin_can_look_up_a_payers_kyc_and_users_only_see_their_own_household(
    world: World,
) -> None:
    parent_id = world.ids["parent"]
    seen = world.call("GET", f"/kyc/status?user_id={parent_id}", "admin")
    assert seen.status_code == 200 and seen.json()["user_id"] == parent_id
    assert world.call("GET", "/kyc/status", "admin").status_code == 403
    assert world.call("GET", f"/kyc/status?user_id={parent_id}", "parent").status_code == 200
    assert world.call("GET", "/kyc/status?user_id=usr_someone_else", "parent").status_code == 404
    assert world.call("GET", f"/kyc/status?user_id={parent_id}", "student").status_code == 200
