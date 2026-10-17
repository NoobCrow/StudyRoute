"""Secrets and personal data must not reach the database file, the audit log, the logs or responses.

An in-process version of scripts/security/leak_scan.py, so the check runs with every `pytest`. Fake
values ("canaries") are planted through the API; each is then searched for in every place a thief
or a log reader could look. A recipient's display name and a document's file name are stored in
plain text on purpose (the family sees them on screen) and are not checked in the database.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tests.helpers import EMAILS, PASSWORD, World

WRONG_PASSWORD = "WrongPass-CANARY-3QxZ!"
CHAT_EMAIL = "canary.person.7f3a@example.org"
CHAT_PHONE = "+8801799900123"
CHAT_PASSPORT = "P7Q3K9X21"
FULL_IBAN = "GB29NWBK60161331926819"
DOC_TEXT = "CANARYDOC-4d9e1b7a"
DOC_PASSPORT = "Q4W8E2R6T"


def database_bytes(world: World) -> bytes:
    """The database file and its write-ahead log, as a thief who copied them would see them."""
    base = Path(world.settings.database_url.removeprefix("sqlite:///"))
    parts = (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm"))
    return b"".join(p.read_bytes() for p in parts if p.exists())


def captured(caplog: pytest.LogCaptureFixture) -> str:
    """Every log line of the test: those from the fixture (setup) and from the test body (call).

    `caplog.text` alone shows only the body, so lines logged while the secrets were planted would be missed.
    """
    records = [*caplog.get_records("setup"), *caplog.get_records("call")]
    return "\n".join(record.getMessage() for record in records)


def whole_audit_log(world: World) -> str:
    events: list[dict] = []
    cursor = None
    while True:
        path = "/audit/events?limit=100" + (f"&cursor={cursor}" if cursor else "")
        page = world.call("GET", path, "admin").json()
        events.extend(page["items"])
        cursor = page.get("next_cursor")
        if not cursor:
            return json.dumps(events)


@pytest.fixture
def planted(world: World, caplog: pytest.LogCaptureFixture) -> dict[str, str]:
    caplog.set_level(logging.DEBUG)
    responses: list[str] = []
    credentials = {"email": EMAILS["parent"], "password": PASSWORD}

    responses.append(
        world.client.post(
            "/api/v1/auth/login", json={**credentials, "password": WRONG_PASSWORD}
        ).text
    )
    login = world.client.post("/api/v1/auth/login", json=credentials)
    responses.append(login.text)
    browser = world.client.post(
        "/api/v1/auth/browser/login",
        headers={"X-StudyRoute-Browser": "1", "Origin": "http://testserver"},
        json=credentials,
    )
    assert browser.status_code == 200, browser.text
    responses.append(browser.text)

    recipient = world.call(
        "POST",
        "/recipients",
        json={
            "type": "UNIVERSITY",
            "display_name": "Canary Recipient Zq9",
            "country": "GB",
            "bic": "EXMPGB2L",
            "iban": FULL_IBAN,
        },
    )
    assert recipient.status_code == 201, recipient.text
    responses.append(recipient.text)
    rid = recipient.json()["recipient_id"]
    proof = world.mfa("parent", "allowlist_recipient", rid)
    responses.append(
        world.call("PATCH", f"/recipients/{rid}", json={"allowlisted": True}, mfa=proof).text
    )
    responses.append(
        world.call(
            "POST",
            "/documents",
            json={
                "kind": "passport",
                "filename": "canary-file.txt",
                "content_text": f"{DOC_TEXT} passport {DOC_PASSPORT}",
            },
        ).text
    )
    message = (
        f"My email is {CHAT_EMAIL}, my phone is {CHAT_PHONE} and my passport is {CHAT_PASSPORT}. "
        "Plan GBP 1,000 tuition by 28 October"
    )
    responses.append(world.call("POST", "/assistant/chat", json={"message": message}).text)
    for path in ("/recipients", "/documents", "/payments", "/quotes"):
        responses.append(world.call("GET", path).text)

    return {
        "access_token": login.json()["access_token"],
        "refresh_token": login.json()["refresh_token"],
        "cookie": world.client.cookies.get("sr_browser_session") or "",
        "mfa_proof": proof,
        "responses": "\n".join(responses),
    }


def test_the_canaries_were_really_issued(planted: dict[str, str]) -> None:
    for name in ("access_token", "refresh_token", "cookie", "mfa_proof"):
        assert len(planted[name]) > 20, name


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("the password", lambda p: PASSWORD),
        ("a wrong password that was typed", lambda p: WRONG_PASSWORD),
        ("the access token", lambda p: p["access_token"]),
        ("the refresh token", lambda p: p["refresh_token"]),
        ("the browser session cookie", lambda p: p["cookie"]),
        ("a one-time MFA proof", lambda p: p["mfa_proof"]),
        ("a full IBAN", lambda p: FULL_IBAN),
        ("an e-mail typed into the chat", lambda p: CHAT_EMAIL),
        ("a phone number typed into the chat", lambda p: CHAT_PHONE),
        ("a passport number typed into the chat", lambda p: CHAT_PASSPORT),
        ("an uploaded document's text", lambda p: DOC_TEXT),
        ("a passport number inside an uploaded document", lambda p: DOC_PASSPORT),
    ],
)
def test_no_secret_is_in_the_database_file(
    planted: dict[str, str], world: World, label, value
) -> None:
    assert value(planted).encode() not in database_bytes(world), label


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("the password", lambda p: PASSWORD),
        ("a wrong password that was typed", lambda p: WRONG_PASSWORD),
        ("the access token", lambda p: p["access_token"]),
        ("the refresh token", lambda p: p["refresh_token"]),
        ("the browser session cookie", lambda p: p["cookie"]),
        ("a one-time MFA proof", lambda p: p["mfa_proof"]),
        ("a full IBAN", lambda p: FULL_IBAN),
        ("an e-mail typed into the chat", lambda p: CHAT_EMAIL),
        ("a phone number typed into the chat", lambda p: CHAT_PHONE),
        ("a passport number typed into the chat", lambda p: CHAT_PASSPORT),
        ("an uploaded document's text", lambda p: DOC_TEXT),
        ("a passport number inside an uploaded document", lambda p: DOC_PASSPORT),
    ],
)
def test_no_secret_is_in_the_audit_log_or_the_logs(
    planted: dict[str, str], world: World, caplog: pytest.LogCaptureFixture, label, value
) -> None:
    needle = value(planted)
    assert needle not in whole_audit_log(world), f"{label} is in the audit log"
    assert needle not in captured(caplog), f"{label} is in the logs"


def test_responses_never_repeat_a_typed_wrong_password_or_a_full_iban(
    planted: dict[str, str],
) -> None:
    assert WRONG_PASSWORD not in planted["responses"]
    assert FULL_IBAN not in planted["responses"]  # recipients are shown masked


def test_the_logs_hold_no_token_shaped_text(
    planted: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    import re

    assert not re.search(
        r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}", captured(caplog)
    )
    assert "BEGIN PRIVATE KEY" not in captured(caplog) and "$argon2" not in captured(caplog)


def test_the_scan_can_really_see_the_database_and_the_logs(
    planted: dict[str, str], world: World, caplog: pytest.LogCaptureFixture
) -> None:
    """A positive control: a value stored in plain text on purpose IS found, so an empty read cannot pass."""
    assert b"Canary Recipient Zq9" in database_bytes(world)
    assert "/api/v1/auth/login" in captured(caplog)
