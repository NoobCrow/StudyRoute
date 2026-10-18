"""Sandbox marking on every response, the sandbox info endpoint and the provider-event trigger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import SecurityMiddleware
from app.core.secret_store import _generate_aes_key, _generate_ec_pem, _generate_hex_secret
from tests.helpers import World


def submitted(world: World, recipient: str | None = None) -> str:
    """A payment that the simulator has submitted and has not settled yet."""
    world.verify_kyc()
    rid = world.recipient_id(recipient) if recipient else world.recipient_id()
    world.allowlist(rid)
    payment = world.draft(recipient_id=rid)
    approval = world.call(
        "POST", f"/payments/{payment['payment_id']}/request-approval", idem=True
    ).json()
    assert world.approve(approval).status_code == 200
    world.clock.advance(3)
    world.ctx.worker.tick()
    pid = str(payment["payment_id"])
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "SUBMITTED"
    return pid


def trigger(world: World, pid: str, outcome: str, who: str | None = "admin") -> Any:
    return world.call(
        "POST", f"/sandbox/payments/{pid}/provider-event", who, json={"outcome": outcome}
    )


# --- X-Sandbox on every response -------------------------------------------------------------
def test_every_response_is_marked_as_sandbox_including_errors(world: World) -> None:
    ok = world.call("GET", "/me")
    unauthenticated = world.client.get("/api/v1/me")
    missing = world.call("GET", "/payments/pay_does_not_exist")
    invalid = world.call("POST", "/quotes", json={"target": {"amount_minor": 0, "currency": "GBP"}})
    for response in (ok, unauthenticated, missing, invalid):
        assert response.headers["x-sandbox"] == "true", response.status_code
    assert (ok.status_code, unauthenticated.status_code) == (200, 401)
    assert (missing.status_code, invalid.status_code) == (404, 422)


def test_the_marker_is_exposed_to_the_browser_and_absent_outside_the_sandbox(world: World) -> None:
    preflight = world.client.options(
        "/api/v1/me",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "GET"},
    )
    exposed = world.client.get("/api/v1/health", headers={"Origin": "http://localhost:8080"})
    assert "X-Sandbox" in exposed.headers["access-control-expose-headers"]
    assert preflight.status_code == 200

    plain = FastAPI()
    plain.get("/ping")(lambda: {"ok": True})
    plain.add_middleware(SecurityMiddleware, max_body_bytes=1000, sandbox=False)
    assert "x-sandbox" not in TestClient(plain).get("/ping").headers


# --- GET /sandbox ----------------------------------------------------------------------------
def test_the_sandbox_description_is_public_and_complete(world: World) -> None:
    response = world.client.get("/api/v1/sandbox")
    assert response.status_code == 200
    body = response.json()
    assert body["sandbox"] is True
    assert "no real money moves" in body["banner"].lower()
    assert {s["token"] for s in body["scenarios"]} == {"FAIL_TEST", "SLOW_TEST", "SANCTION_TEST"}
    assert {p["provider_id"] for p in body["providers"]} == {"prov_a", "prov_b", "prov_c"}
    assert all(p["name"].endswith("(synthetic)") for p in body["providers"])
    simulated = " ".join(item["component"] for item in body["simulated"]).lower()
    for part in ("providers", "exchange rates", "kyc", "swift", "settlement"):
        assert part in simulated
    assert body["timings"]["quote_ttl_seconds"] == 300
    assert body["timings"]["mfa_proof_ttl_seconds"] == 300
    assert body["limits"]["indicative"].startswith("Sandbox caps")
    assert "Confirm with your AD bank" in body["disclaimer"]
    assert body["ai_mode"] == "template"


def test_the_sandbox_description_never_leaks_secrets(world: World) -> None:
    text = world.client.get("/api/v1/sandbox").text
    for secret in world.ctx.secrets.webhook_secrets("prov_a"):
        assert secret not in text
    assert "BEGIN" not in text


# --- the provider-event trigger --------------------------------------------------------------
def test_an_admin_can_fail_a_submitted_payment_through_the_signed_webhook(world: World) -> None:
    pid = submitted(world)
    reply = trigger(world, pid, "fail")
    assert reply.status_code == 200
    assert reply.json()["event"] == "payment.failed"
    assert reply.json()["simulated"] is True
    world.ctx.worker.tick()
    detail = world.call("GET", f"/payments/{pid}").json()
    assert detail["state"] == "FAILED"
    sent = world.dispatcher.sent[-1]
    assert sent[1]["X-Signature"].startswith("t="), "it went through the real webhook path"
    assert world.audit_rows(action="sandbox.provider_event_scheduled", payment_id=pid)
    assert world.audit_rows(action="webhook.accepted", payment_id=pid)


def make_slow_recipient(world: World) -> str:
    """A SLOW_TEST recipient with a valid synthetic IBAN (check digits worked out here)."""
    bban = "EXMP12345600007777"
    digits = "".join(str(int(c, 36)) for c in bban + "GB00")
    iban = f"GB{98 - int(digits) % 97:02d}{bban}"
    created = world.call(
        "POST",
        "/recipients",
        json={
            "type": "UNIVERSITY",
            "display_name": "SLOW_TEST College (synthetic)",
            "country": "GB",
            "bic": "EXMPGB2L",
            "iban": iban,
        },
    )
    assert created.status_code == 201, created.text
    return str(created.json()["recipient_id"])


def test_an_admin_can_settle_a_slow_payment_without_waiting_thirty_seconds(
    world: World,
) -> None:
    make_slow_recipient(world)
    pid = submitted(world, recipient="SLOW_TEST College (synthetic)")
    world.clock.advance(10)
    world.ctx.worker.tick()
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "SUBMITTED", "still in flight"
    assert trigger(world, pid, "settle").status_code == 200
    world.ctx.worker.tick()
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "SETTLED"


def test_only_an_admin_may_trigger_provider_events(world: World) -> None:
    pid = submitted(world)
    assert trigger(world, pid, "fail", None).status_code == 401
    assert trigger(world, pid, "fail", "parent").status_code == 403
    assert trigger(world, pid, "fail", "student").status_code == 403
    ai = world.client.post(
        f"/api/v1/sandbox/payments/{pid}/provider-event",
        headers=world.ai_headers(),
        json={"outcome": "fail"},
    )
    assert ai.status_code == 403
    assert world.call("GET", f"/payments/{pid}").json()["state"] == "SUBMITTED"


def test_a_payment_that_is_not_in_flight_cannot_be_triggered(world: World) -> None:
    world.verify_kyc()
    world.allowlist()
    draft = world.draft()
    early = trigger(world, draft["payment_id"], "settle")
    assert (early.status_code, early.json()["code"]) == (409, "INVALID_STATE")
    pid = submitted(world)
    assert trigger(world, pid, "settle").status_code == 200
    world.ctx.worker.tick()
    late = trigger(world, pid, "fail")
    assert (late.status_code, late.json()["code"]) == (409, "INVALID_STATE")


def test_unknown_payments_and_bad_outcomes_are_refused(world: World) -> None:
    assert trigger(world, "pay_nope", "settle").status_code == 404
    pid = submitted(world)
    bad = trigger(world, pid, "explode")
    assert (bad.status_code, bad.json()["code"]) == (422, "VALIDATION_FAILED")


# --- production mode -------------------------------------------------------------------------
@pytest.fixture
def production_world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JWT_PRIVATE_KEY_PEM", _generate_ec_pem().replace("\n", chr(92) + "n"))
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", _generate_aes_key())
    for provider in ("PROV_A", "PROV_B", "PROV_C"):
        monkeypatch.setenv(f"WEBHOOK_SECRET_{provider}", _generate_hex_secret())
    instance = World(tmp_path, app_env="production")
    yield instance
    instance.close()


def test_production_mode_has_no_sandbox_surface_and_no_marker(production_world: World) -> None:
    world = production_world
    assert world.client.get("/api/v1/sandbox").status_code == 404
    assert "x-sandbox" not in world.client.get("/api/v1/health").headers
    assert "demo" not in world.client.get("/api/v1/health").json()
    reply = trigger(world, "pay_x", "settle")
    assert reply.status_code == 404
    assert "x-sandbox" not in reply.headers


def test_the_demo_hints_can_be_switched_off(tmp_path: Path) -> None:
    quiet = World(tmp_path, show_demo_hints=False)
    try:
        assert "demo" not in quiet.client.get("/api/v1/health").json()
        assert quiet.client.get("/api/v1/sandbox").json()["demo"] is None
    finally:
        quiet.close()
