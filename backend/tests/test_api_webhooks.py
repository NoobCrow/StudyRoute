"""Signed provider webhooks: T12 (bad signature), T13 (replay window), T14 (duplicates)."""

from __future__ import annotations

import json
from typing import Any

from app.providers.webhooks import build_header
from tests.helpers import World


def submitted_payment(world: World) -> dict[str, Any]:
    approval = world.ready_payment()
    assert world.approve(approval).status_code == 200
    world.clock.advance(4)
    assert world.ctx.worker.tick()["payments_submitted"] == 1
    payment = world.call("GET", f"/payments/{approval['payment_id']}").json()
    assert payment["state"] == "SUBMITTED"
    return payment


def signed(world: World, payment: dict[str, Any], *, event: str = "payment.settled",
           event_id: str = "evt_test_0001", age: int = 0, provider: str = "prov_b",
           secret: str | None = None) -> tuple[bytes, dict[str, str]]:  # fmt: skip
    body = {"event": event, "payment_id": payment["payment_id"], "uetr": payment["uetr"],
            "occurred_at": "2026-10-14T05:00:10Z"}  # fmt: skip
    raw = json.dumps(body, separators=(",", ":")).encode()
    key = secret or world.ctx.secrets.webhook_secrets(provider)[0]
    stamp = int(world.clock.now().timestamp()) - age
    headers = {"X-Signature": build_header(key, stamp, raw), "X-Event-Id": event_id,
               "Content-Type": "application/json"}  # fmt: skip
    return raw, headers


def send(world: World, raw: bytes, headers: dict[str, str]):
    return world.client.post("/api/v1/webhooks/provider", content=raw, headers=headers)


def state_of(world: World, payment: dict[str, Any]) -> str:
    return str(world.call("GET", f"/payments/{payment['payment_id']}").json()["state"])


def test_a_correctly_signed_webhook_settles_the_payment(world: World) -> None:
    payment = submitted_payment(world)
    response = send(world, *signed(world, payment))
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert state_of(world, payment) == "SETTLED"
    tracker = world.call("GET", f"/payments/{payment['payment_id']}/tracker").json()
    assert [t["state"] for t in tracker["timeline"]][-3:] == ["APPROVED", "SUBMITTED", "SETTLED"]
    assert tracker["uetr"] == payment["uetr"]
    assert world.audit_rows(action="webhook.accepted", payment_id=payment["payment_id"])
    changed = world.audit_rows(action="payment.state_changed", actor_type="provider")
    assert changed[0]["detail"] == "SUBMITTED>SETTLED via provider_settled"


def test_T12_bad_signature_is_401_audited_and_changes_nothing(world: World) -> None:
    payment = submitted_payment(world)
    raw, headers = signed(world, payment, secret="not-the-provider-secret")
    response = send(world, raw, headers)
    assert response.status_code == 401
    assert state_of(world, payment) == "SUBMITTED"
    rejected = world.audit_rows(action="webhook.rejected")
    assert len(rejected) == 1
    assert rejected[0]["reason_code"] == "BAD_SIGNATURE"
    assert rejected[0]["decision"] == "blocked"


def test_T12_changing_even_the_whitespace_of_the_body_breaks_the_signature(world: World) -> None:
    payment = submitted_payment(world)
    raw, headers = signed(world, payment)
    assert send(world, raw.replace(b",", b", "), headers).status_code == 401
    assert state_of(world, payment) == "SUBMITTED"


def test_T12_missing_or_malformed_signature_headers(world: World) -> None:
    payment = submitted_payment(world)
    raw, headers = signed(world, payment)
    assert send(world, raw, {k: v for k, v in headers.items() if k != "X-Signature"}).status_code == 401
    assert send(world, raw, {**headers, "X-Signature": "v1=abc"}).status_code == 401
    assert state_of(world, payment) == "SUBMITTED"


def test_T13_a_webhook_older_than_five_minutes_is_rejected_as_a_replay(world: World) -> None:
    payment = submitted_payment(world)
    response = send(world, *signed(world, payment, age=301))
    assert response.status_code == 401
    assert state_of(world, payment) == "SUBMITTED"
    assert world.audit_rows(action="webhook.rejected")[0]["reason_code"] == "REPLAY_WINDOW"


def test_T14_the_same_event_twice_returns_200_and_transitions_once(world: World) -> None:
    payment = submitted_payment(world)
    raw, headers = signed(world, payment)
    first = send(world, raw, headers)
    second = send(world, raw, headers)
    assert first.status_code == second.status_code == 200
    assert second.json() == {"received": True, "duplicate": True}
    settled = [
        r for r in world.audit_rows(payment_id=payment["payment_id"])
        if r["detail"] == "SUBMITTED>SETTLED via provider_settled"
    ]  # fmt: skip
    assert len(settled) == 1


def test_a_second_settlement_with_a_new_event_id_is_a_conflict(world: World) -> None:
    payment = submitted_payment(world)
    assert send(world, *signed(world, payment, event_id="evt_test_a")).status_code == 200
    again = send(world, *signed(world, payment, event_id="evt_test_b"))
    assert again.status_code == 409
    assert again.json()["code"] == "INVALID_STATE"


def test_a_provider_cannot_settle_another_providers_payment(world: World) -> None:
    payment = submitted_payment(world)  # routed through prov_b
    response = send(world, *signed(world, payment, provider="prov_a"))
    assert response.status_code == 422
    assert state_of(world, payment) == "SUBMITTED"


def test_bad_bodies_with_a_valid_signature(world: World) -> None:
    payment = submitted_payment(world)
    raw = b"not json"
    key = world.ctx.secrets.webhook_secrets("prov_b")[0]
    stamp = int(world.clock.now().timestamp())
    headers = {"X-Signature": build_header(key, stamp, raw), "X-Event-Id": "evt_test_bad"}
    assert send(world, raw, headers).status_code == 400
    no_event_id = {"X-Signature": headers["X-Signature"]}
    assert send(world, raw, no_event_id).status_code == 400
    assert state_of(world, payment) == "SUBMITTED"


def test_a_failed_event_marks_the_payment_failed(world: World) -> None:
    payment = submitted_payment(world)
    assert send(world, *signed(world, payment, event="payment.failed")).status_code == 200
    assert state_of(world, payment) == "FAILED"
