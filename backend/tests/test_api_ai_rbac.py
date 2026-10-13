"""The AI service account is read/draft only (T09)."""

from __future__ import annotations

from app.domain.constants import ActorKind
from tests.helpers import World


def test_T09_the_ai_token_can_never_approve_and_the_attempt_is_audited(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    response = world.client.post(
        f"/api/v1/payments/{pid}/approve",
        headers={
            **world.ai_headers(),
            "Idempotency-Key": "3b241101-e2bb-4255-8caf-4136c566a962",
            "X-MFA-Proof": world.mfa("parent", "approve_payment", pid),
        },
        json={"confirm_summary_hash": approval["summary_hash"]},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "AI_CANNOT_APPROVE"
    blocked = world.audit_rows(action="approval.blocked", reason_code="AI_CANNOT_APPROVE")
    assert len(blocked) == 1
    assert blocked[0]["actor_type"] == "ai"
    assert blocked[0]["decision"] == "blocked"
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "PENDING_APPROVAL"


def test_the_ai_token_is_refused_every_other_privileged_action(world: World) -> None:
    approval = world.ready_payment()
    pid = approval["payment_id"]
    ai = world.ai_headers()
    key = {"Idempotency-Key": "9d8f7e6c-5b4a-4321-8abc-0123456789ab"}
    rid = world.recipient_id()
    config = {"key": "limits.daily_usd_equivalent", "value": 10**7, "reason": "please"}
    attempts = [
        ("POST", f"/payments/{pid}/cancel", {}),
        ("POST", f"/payments/{pid}/reject", {}),
        ("PATCH", f"/recipients/{rid}", {"allowlisted": True}),
        ("PUT", "/config/rules", config),
        ("PUT", "/kyc/mock-review", {"user_id": world.ids["parent"], "status": "VERIFIED"}),
    ]
    for method, path, body in attempts:
        response = world.client.request(method, f"/api/v1{path}", headers={**ai, **key}, json=body)
        assert response.status_code == 403, (method, path)
    assert world.client.get("/api/v1/audit/events", headers=ai).status_code == 403
    assert world.client.get("/api/v1/audit/verify", headers=ai).status_code == 403


def test_the_ai_service_may_read_and_draft_as_the_matrix_allows(world: World) -> None:
    ai = world.ai_headers()
    target = {"amount_minor": 500_000, "currency": "GBP"}
    quote = world.client.post(
        "/api/v1/quotes", headers=ai, json={"target": target, "destination_country": "GB"}
    )
    assert quote.status_code == 201
    assert world.client.get("/api/v1/payments", headers=ai).status_code == 200
    draft = world.client.post(
        "/api/v1/payments",
        headers={**ai, "Idempotency-Key": "11111111-2222-4333-8444-555555555555"},
        json={
            "quote_id": quote.json()["quote_id"],
            "provider_id": "prov_b",
            "recipient_id": world.recipient_id(),
            "reference": "AI-DRAFT-1",
        },
    )
    assert draft.status_code == 201
    created = world.audit_rows(action="payment.created")[0]
    assert created["actor_type"] == "ai"
    assert created["decision"] == "suggested"


def test_a_forged_ai_token_without_a_parent_is_rejected(world: World) -> None:
    token, _ = world.ctx.tokens.issue(
        user_id="usr_ai_service", kind=ActorKind.AI, scopes=frozenset(), now=world.clock.now()
    )
    response = world.client.get("/api/v1/payments", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
