"""Headers, CORS, body limits, XSS handling (T23) and log privacy (T24)."""

from __future__ import annotations

import logging

import pytest

from app.core.config import Settings
from app.core.logging import redact
from app.core.secret_store import MissingSecretError, SecretStore
from tests.helpers import World

IBAN = "GB08EXMP12345612344821"
SPACED = "GB08 EXMP 1234 5612 3448 21"


def test_security_headers_are_on_every_response_including_errors(world: World) -> None:
    for response in (
        world.client.get("/health"),
        world.client.get("/api/v1/me"),
        world.client.get("/nope"),
    ):
        headers = response.headers
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
        assert "max-age=" in headers["strict-transport-security"]
        assert headers["x-frame-options"] == "DENY"
        assert "default-src 'none'" in headers["content-security-policy"]
        assert "frame-ancestors 'none'" in headers["content-security-policy"]
        assert headers["cache-control"] == "no-store"


def test_cors_allows_only_the_configured_origins_without_credentials(world: World) -> None:
    allowed = world.client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:8080"
    assert "access-control-allow-credentials" not in allowed.headers
    denied = world.client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers
    preflight = world.client.options(
        "/api/v1/payments",
        headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] != "*"


def test_oversized_bodies_are_refused_before_they_are_read(world: World) -> None:
    big = b'{"x":"' + b"a" * 70_000 + b'"}'
    response = world.client.post(
        "/api/v1/auth/login", content=big, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert response.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_a_bad_request_id_is_replaced(world: World) -> None:
    response = world.client.get("/health", headers={"X-Request-Id": "bad id with spaces!"})
    assert response.headers["x-request-id"].startswith("req_")


def test_T23_script_text_in_a_recipient_name_is_kept_as_inert_data(world: World) -> None:
    payload = "<script>alert(1)</script>"
    response = world.call(
        "POST", "/recipients",
        json={"type": "UNIVERSITY", "display_name": payload, "country": "GB",
              "bic": "EXMPGB2L", "iban": IBAN},
    )  # fmt: skip
    assert response.status_code == 201
    assert response.json()["display_name"] == payload
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "script-src" not in response.headers["content-security-policy"]
    listing = world.call("GET", "/recipients")
    assert listing.headers["content-type"].startswith("application/json")
    assert payload in [r["display_name"] for r in listing.json()["items"]]


def test_control_characters_are_stripped_from_names(world: World) -> None:
    response = world.call(
        "POST", "/recipients",
        json={"type": "UNIVERSITY", "display_name": "Evil\x00\x1b[31m  Name\n\tLtd", "country": "GB",
              "bic": "EXMPGB2L", "iban": IBAN},
    )  # fmt: skip
    assert response.status_code == 201
    assert "\x00" not in response.json()["display_name"]
    assert "\n" not in response.json()["display_name"]


def test_T24_full_account_numbers_never_reach_the_logs(world: World, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    created = world.call(
        "POST", "/recipients",
        json={"type": "UNIVERSITY", "display_name": "Log Test College", "country": "GB",
              "bic": "EXMPGB2L", "iban": SPACED},
    )  # fmt: skip
    assert created.status_code == 201
    approval = world.ready_payment()
    world.call("GET", f"/payments/{approval['payment_id']}/instruction-preview")
    world.approve(approval)
    logging.getLogger("studyroute.test").warning("accidental leak %s and %s", IBAN, SPACED)
    logging.getLogger("studyroute.test").error("failure", exc_info=ValueError(f"bad {IBAN}"))
    text = "\n".join(f"{r.getMessage()} {r.exc_text or ''}" for r in caplog.records)
    for secret in (IBAN, SPACED, IBAN[-12:], "12345612344821"):
        assert secret not in text
    token = world.login("parent")["Authorization"].split()[1]
    assert token not in text


def test_the_redaction_helper_removes_tokens_emails_and_numbers() -> None:
    sample = (
        "Authorization: Bearer abcdefghijklmnop user a.b@example.test pw password=hunter22 "
        "acct 12345678901 jwt eyJhbGciOiJFUzI1NiJ9.eyJzdWIiOiJ1In0.c2lnbmF0dXJlX2hlcmU"
    )
    cleaned = redact(sample)
    for leaked in ("abcdefghijklmnop", "a.b@example.test", "hunter22", "12345678901", "eyJhbGci"):
        assert leaked not in cleaned
    assert redact("rate 1.58 percent, BDT 25,300.00") == "rate 1.58 percent, BDT 25,300.00"


def test_production_mode_refuses_to_invent_secrets(tmp_path, monkeypatch) -> None:
    for name in ("JWT_PRIVATE_KEY_PEM", "DATA_ENCRYPTION_KEY", "WEBHOOK_SECRET_PROV_A"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(app_env="production", data_dir=tmp_path)
    assert settings.sandbox_mfa_code is None
    with pytest.raises(MissingSecretError):
        SecretStore(settings).assert_ready(["prov_a"])


def test_interactive_docs_are_sandbox_only_with_their_own_csp(world: World) -> None:
    docs = world.client.get("/api/v1/docs")
    assert docs.status_code == 200
    assert "cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert world.client.get("/api/v1/openapi.json").status_code == 200
