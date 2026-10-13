"""Small, boring crypto helpers built on `cryptography` and the standard library.

No custom primitives: AES-256-GCM for fields, SHA-256 for hashes, HMAC-SHA256 for webhooks.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_VERSION = "v1"


class DecryptionError(Exception):
    """Raised when a stored ciphertext cannot be authenticated."""


class FieldCipher:
    """AES-256-GCM for sensitive columns. The context string binds a value to its row."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = os.urandom(12)
        sealed = self._aead.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
        encoded = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
        return f"{_VERSION}.{encoded}"

    def decrypt(self, token: str, *, context: str) -> str:
        try:
            version, _, payload = token.partition(".")
            if version != _VERSION:
                raise DecryptionError("unknown ciphertext version")
            raw = base64.urlsafe_b64decode(payload.encode("ascii"))
            nonce, sealed = raw[:12], raw[12:]
            return self._aead.decrypt(nonce, sealed, context.encode("utf-8")).decode("utf-8")
        except (InvalidTag, ValueError) as exc:
            raise DecryptionError("ciphertext failed authentication") from exc


def canonical_json(value: Any) -> bytes:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def sha256_ref(data: bytes | str) -> str:
    """Hash in the sha256:<hex> form used by the API."""
    return f"sha256:{sha256_hex(data)}"


def hash_object(value: Any) -> str:
    return sha256_ref(canonical_json(value))


def hmac_sha256_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
