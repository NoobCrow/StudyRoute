"""Prefixed, time-ordered identifiers such as pay_01J9..., built on ULIDs."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    chars: list[str] = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid() -> str:
    millis = time.time_ns() // 1_000_000
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode(millis, 10) + _encode(randomness, 16)


def new_id(prefix: str) -> str:
    return f"{prefix}_{new_ulid()}"
