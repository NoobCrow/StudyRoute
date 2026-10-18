"""HMAC-signed webhooks (blueprint 8.5).

    signed_payload = timestamp + "." + raw_request_body
    signature      = HMAC_SHA256(webhook_secret, signed_payload) -> hex
    header         = "t=" + timestamp + ",v1=" + signature

The receiver reads the RAW body, checks the timestamp window, recomputes the HMAC and
compares in constant time. Event-id de-duplication happens in the API layer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from app.core.crypto import constant_time_equals, hmac_sha256_hex

TOLERANCE_SECONDS = 300


class WebhookRejected(Exception):
    """The webhook failed verification. `reason_code` goes to the audit log."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.message = message


def sign(secret: str, timestamp: int, body: bytes) -> str:
    return hmac_sha256_hex(secret, f"{timestamp}.".encode("ascii") + body)


def build_header(secret: str, timestamp: int, body: bytes) -> str:
    return f"t={timestamp},v1={sign(secret, timestamp, body)}"


def parse_header(header: str | None) -> tuple[int, list[str]]:
    """Split "t=...,v1=...[,v1=...]" into the timestamp and the candidate signatures."""
    if not header:
        raise WebhookRejected("MISSING_SIGNATURE", "The X-Signature header is missing.")
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        name, _, value = part.strip().partition("=")
        if name == "t" and value.isdigit():
            timestamp = int(value)
        elif name == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise WebhookRejected("MALFORMED_SIGNATURE", "The X-Signature header is malformed.")
    return timestamp, signatures


def verify(
    header: str | None,
    body: bytes,
    secrets_by_provider: Mapping[str, Sequence[str]],
    now: datetime,
    tolerance_seconds: int = TOLERANCE_SECONDS,
) -> str:
    """Return the provider whose secret signed this body, or raise WebhookRejected."""
    timestamp, candidates = parse_header(header)
    if abs(int(now.timestamp()) - timestamp) > tolerance_seconds:
        raise WebhookRejected("REPLAY_WINDOW", "The timestamp is outside the 5 minute window.")
    matched: str | None = None
    for provider_id, secrets in secrets_by_provider.items():
        for secret in secrets:
            expected = sign(secret, timestamp, body)
            for candidate in candidates:
                if constant_time_equals(expected, candidate) and matched is None:
                    matched = provider_id
    if matched is None:
        raise WebhookRejected("BAD_SIGNATURE", "The signature does not match.")
    return matched
