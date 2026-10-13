"""Input validation and the RFC 7807 error format (T02, T03)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text

GB_IBAN = "GB08EXMP12345612344821"


def quote_body(**target: Any) -> dict[str, Any]:
    return {
        "target": {"amount_minor": 1_000_000, "currency": "GBP", **target},
        "purpose": "TUITION",
        "destination_country": "GB",
        "charge_code": "OUR",
    }


def recipient_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "type": "UNIVERSITY",
        "display_name": "Test University (synthetic)",
        "country": "GB",
        "bic": "EXMPGB2L",
        "iban": GB_IBAN,
    }
    body.update(overrides)
    return body


@pytest.mark.parametrize("amount", [0, -1, -250_000])
def test_T02_zero_or_negative_amount_is_validation_failed(world, amount) -> None:
    response = world.call("POST", "/quotes", json=quote_body(amount_minor=amount))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_T02_a_float_amount_is_refused_because_money_is_never_a_float(world) -> None:
    response = world.call("POST", "/quotes", json=quote_body(amount_minor=100.5))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


@pytest.mark.parametrize("currency", ["XYZ", "JPY", "BDT"])
def test_T02_unsupported_currency_is_validation_failed(world, currency) -> None:
    response = world.call("POST", "/quotes", json=quote_body(currency=currency))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_currency_must_match_the_destination_country(world) -> None:
    response = world.call("POST", "/quotes", json=quote_body(currency="USD"))
    assert response.status_code == 422
    assert "GBP" in response.json()["detail"]


def test_unknown_destination_charge_code_and_purpose_are_rejected(world) -> None:
    for patch in ({"destination_country": "ZZ"}, {"charge_code": "XXX"}, {"purpose": "GIFT"}):
        body = {**quote_body(), **patch}
        assert world.call("POST", "/quotes", json=body).status_code == 422


def test_errors_use_the_rfc_7807_problem_format(world) -> None:
    response = world.call("POST", "/quotes", json=quote_body(amount_minor=0))
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert {"type", "title", "status", "code", "detail", "request_id"} <= set(body)
    assert body["status"] == 422
    assert body["request_id"] == response.headers["x-request-id"]


def test_validation_errors_never_echo_the_submitted_value(world) -> None:
    response = world.client.post(
        "/api/v1/auth/login", json={"email": "x@example.test", "password": 12345678}
    )
    assert response.status_code == 422
    assert "12345678" not in response.text


def test_unknown_fields_are_rejected(world) -> None:
    body = {**quote_body(), "is_admin": True}
    assert world.call("POST", "/quotes", json=body).status_code == 422


def test_malformed_json_is_a_400(world) -> None:
    response = world.client.post(
        "/api/v1/quotes", content=b"{not json", headers={**world.login("parent"), "Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "BAD_REQUEST"


def test_request_id_from_the_client_is_echoed(world) -> None:
    response = world.client.get("/health", headers={"X-Request-Id": "client-req-123"})
    assert response.headers["x-request-id"] == "client-req-123"


def test_T03_one_changed_digit_in_the_iban_is_invalid_iban(world) -> None:
    response = world.call("POST", "/recipients", json=recipient_body(iban="GB08EXMP12345612344822"))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_IBAN"


def test_invalid_bic_is_reported_as_invalid_bic(world) -> None:
    response = world.call("POST", "/recipients", json=recipient_body(bic="EXMPG"))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_BIC"


def test_iban_country_must_match_the_recipient_country(world) -> None:
    response = world.call("POST", "/recipients", json=recipient_body(iban="DE54370400440532013048"))
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_FAILED"


def test_a_valid_recipient_is_returned_masked_and_stored_encrypted(world) -> None:
    response = world.call("POST", "/recipients", json=recipient_body())
    assert response.status_code == 201
    body = response.json()
    assert body["account_masked"] == "GB** **** 4821"
    assert body["allowlisted"] is False
    assert GB_IBAN not in response.text
    with world.ctx.db.read() as session:
        stored = session.execute(
            text("SELECT iban_or_account_enc, account_last4 FROM recipients WHERE id = :id"),
            {"id": body["recipient_id"]},
        ).one()
    assert GB_IBAN not in stored[0]
    assert stored[1] == "4821"


def test_uk_domestic_details_and_us_aba_are_validated(world) -> None:
    uk = recipient_body(iban=None, routing_code="12-34-56", account_number="12345678")
    assert world.call("POST", "/recipients", json=uk).status_code == 201
    bad_uk = recipient_body(iban=None, routing_code="12345", account_number="12345678")
    assert world.call("POST", "/recipients", json=bad_uk).status_code == 422
    us = {
        "type": "UNIVERSITY", "display_name": "US University (synthetic)", "country": "US",
        "bic": "EXMPUS33", "routing_code": "123456780", "account_number": "000123456789",
    }  # fmt: skip
    assert world.call("POST", "/recipients", json=us).status_code == 201
    assert world.call("POST", "/recipients", json={**us, "routing_code": "123456789"}).status_code == 422
