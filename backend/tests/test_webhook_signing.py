"""HMAC signing and verification primitives (blueprint 8.5; T12, T13 at unit level)."""

from datetime import UTC, datetime

import pytest

from app.providers import webhooks as wh

NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
TS = int(NOW.timestamp())
BODY = b'{"event":"payment.settled","payment_id":"pay_1"}'
SECRETS = {"prov_a": ["secret-a"], "prov_b": ["secret-b", "secret-b-old"]}


def test_header_format_and_signed_payload() -> None:
    header = wh.build_header("secret-a", TS, BODY)
    assert header.startswith(f"t={TS},v1=")
    assert header.split("v1=")[1] == wh.sign("secret-a", TS, BODY)
    assert len(wh.sign("secret-a", TS, BODY)) == 64


def test_valid_signature_identifies_the_provider() -> None:
    assert wh.verify(wh.build_header("secret-a", TS, BODY), BODY, SECRETS, NOW) == "prov_a"
    assert wh.verify(wh.build_header("secret-b", TS, BODY), BODY, SECRETS, NOW) == "prov_b"


def test_previous_secret_is_accepted_during_rotation() -> None:
    assert wh.verify(wh.build_header("secret-b-old", TS, BODY), BODY, SECRETS, NOW) == "prov_b"


def test_T12_bad_signature_is_rejected() -> None:
    with pytest.raises(wh.WebhookRejected) as caught:
        wh.verify(f"t={TS},v1={'0' * 64}", BODY, SECRETS, NOW)
    assert caught.value.reason_code == "BAD_SIGNATURE"


def test_tampered_body_is_rejected() -> None:
    header = wh.build_header("secret-a", TS, BODY)
    with pytest.raises(wh.WebhookRejected) as caught:
        wh.verify(header, BODY + b" ", SECRETS, NOW)
    assert caught.value.reason_code == "BAD_SIGNATURE"


@pytest.mark.parametrize("age", [301, -301, 3600])
def test_T13_timestamp_outside_five_minutes_is_a_replay(age: int) -> None:
    stale = TS - age
    with pytest.raises(wh.WebhookRejected) as caught:
        wh.verify(wh.build_header("secret-a", stale, BODY), BODY, SECRETS, NOW)
    assert caught.value.reason_code == "REPLAY_WINDOW"


def test_exactly_five_minutes_is_still_accepted() -> None:
    header = wh.build_header("secret-a", TS - 300, BODY)
    assert wh.verify(header, BODY, SECRETS, NOW) == "prov_a"


@pytest.mark.parametrize(
    ("header", "reason"),
    [
        (None, "MISSING_SIGNATURE"),
        ("", "MISSING_SIGNATURE"),
        ("garbage", "MALFORMED_SIGNATURE"),
        ("t=abc,v1=deadbeef", "MALFORMED_SIGNATURE"),
        (f"t={TS}", "MALFORMED_SIGNATURE"),
    ],
)
def test_missing_or_malformed_headers(header: str | None, reason: str) -> None:
    with pytest.raises(wh.WebhookRejected) as caught:
        wh.verify(header, BODY, SECRETS, NOW)
    assert caught.value.reason_code == reason


def test_several_v1_values_are_supported() -> None:
    good = wh.sign("secret-a", TS, BODY)
    header = f"t={TS},v1={'1' * 64},v1={good}"
    assert wh.verify(header, BODY, SECRETS, NOW) == "prov_a"


def test_a_signature_for_one_provider_does_not_match_another_secret() -> None:
    with pytest.raises(wh.WebhookRejected):
        wh.verify(wh.build_header("not-a-secret", TS, BODY), BODY, SECRETS, NOW)
