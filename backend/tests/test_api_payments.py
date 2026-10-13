"""Payment lifecycle: happy path, quote expiry (T06) and the KYC gate (T07)."""

from __future__ import annotations

from tests.helpers import World


def test_happy_path_to_approved(world: World) -> None:
    approval = world.ready_payment()
    assert approval["state"] == "PENDING_APPROVAL"
    summary = approval["summary"]
    assert summary["recipient"].endswith("GB** **** 4821")
    assert summary["total_cost_bdt_minor"] == 2_530_000
    assert summary["parent_pays_bdt_minor"] == 162_530_000
    assert summary["latest_send_date"] == "2026-10-20"
    assert "No real money moves" in summary["disclaimer"]
    done = world.approve(approval)
    assert done.status_code == 200
    body = done.json()
    assert body["state"] == "APPROVED"
    assert body["approved_by"] == world.ids["parent"]


def test_T06_approving_after_the_quote_expired_is_409_and_returns_to_draft(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    world.clock.advance(301)
    proof = world.mfa("parent", "approve_payment", pid)  # fresh proof: only the quote is stale
    response = world.approve(approval, mfa=proof)
    assert response.status_code == 409
    assert response.json()["code"] == "QUOTE_EXPIRED"
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "DRAFT"
    changes = [r["detail"] for r in world.audit_rows(payment_id=pid, reason_code="QUOTE_EXPIRED")]
    assert changes == ["PENDING_APPROVAL>DRAFT via quote_expired"]


def test_after_expiry_a_new_quote_can_be_attached_to_the_same_draft(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    world.clock.advance(301)
    world.approve(approval, mfa=world.mfa("parent", "approve_payment", pid))
    fresh = world.quote()
    requote = world.call(
        "POST", f"/payments/{pid}/requote", idem=True,
        json={"quote_id": fresh["quote_id"], "provider_id": "prov_b"},
    )  # fmt: skip
    assert requote.status_code == 200
    assert requote.json()["state"] == "QUOTED"
    again = world.call("POST", f"/payments/{pid}/request-approval", idem=True)
    assert again.status_code == 200
    assert world.approve(again.json()).status_code == 200


def test_requote_must_match_the_original_amount(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    world.clock.advance(301)
    world.approve(approval, mfa=world.mfa("parent", "approve_payment", pid))
    other = world.quote(target={"amount_minor": 2_000_000, "currency": "GBP"})
    response = world.call(
        "POST", f"/payments/{pid}/requote", idem=True,
        json={"quote_id": other["quote_id"], "provider_id": "prov_b"},
    )  # fmt: skip
    assert response.status_code == 422


def test_the_worker_sweeps_expired_quotes_back_to_draft(world: World) -> None:
    approval = world.ready_payment()
    world.clock.advance(301)
    assert world.ctx.worker.tick()["quotes_expired"] == 1
    assert world.call("GET", f"/payments/{approval['payment_id']}").json()["state"] == "DRAFT"


def test_T07_approve_while_kyc_is_pending_is_kyc_not_verified(world: World) -> None:
    approval = world.ready_payment()
    pending = {"user_id": world.ids["parent"], "status": "PENDING"}
    assert world.call("PUT", "/kyc/mock-review", "admin", json=pending).status_code == 200
    response = world.approve(approval)
    assert response.status_code == 422
    assert response.json()["code"] == "KYC_NOT_VERIFIED"
    blocked = world.audit_rows(action="approval.blocked", reason_code="KYC_NOT_VERIFIED")
    assert len(blocked) == 1 and blocked[0]["decision"] == "blocked"


def test_T07_requesting_approval_is_also_blocked_until_kyc_is_verified(world: World) -> None:
    world.allowlist()
    payment = world.draft()
    detail = world.call("GET", f"/payments/{payment['payment_id']}").json()
    assert detail["readiness"]["can_request_approval"] is False
    assert [b["code"] for b in detail["readiness"]["blockers"]] == ["KYC_NOT_VERIFIED"]
    assert detail["summary_preview"]["parent_pays_bdt_minor"] == 162_530_000
    path = f"/payments/{payment['payment_id']}/request-approval"
    response = world.call("POST", path, idem=True)
    assert response.status_code == 422
    assert response.json()["code"] == "KYC_NOT_VERIFIED"
