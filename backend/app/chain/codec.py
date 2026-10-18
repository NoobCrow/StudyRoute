"""ABI encoding and decoding for the sandbox contracts, built on eth-abi.

No hashing happens here: function selectors and event topics were computed when the contracts
were compiled and are stored in the artifacts.
"""

from __future__ import annotations

import re
from typing import Any

from eth_abi import decode, encode

from app.chain.artifacts import Artifact, EventAbi

ERROR_SELECTOR = bytes.fromhex("08c379a0")  # Error(string), what require(cond, "text") reverts with


class DecodeError(ValueError):
    pass


def to_address(value: str) -> str:
    """Lower-case 0x address. Mixed-case would need a checksum, which needs a hash library."""
    text = value.lower()
    if not re.fullmatch(r"0x[0-9a-f]{40}", text):
        raise DecodeError(f"Not an address: {value!r}")
    return text


def _normalise(type_name: str, value: Any) -> Any:
    if type_name == "address":
        return to_address(str(value))
    if type_name.startswith("bytes") and isinstance(value, str):
        return bytes.fromhex(value.removeprefix("0x"))
    if type_name.endswith("[]"):
        inner = type_name[:-2]
        return [_normalise(inner, item) for item in value]
    return value


def _plain(type_name: str, value: Any) -> Any:
    """Make a decoded value JSON friendly: addresses lower case, bytes as 0x hex."""
    if type_name == "address":
        return to_address(str(value))
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, tuple | list):
        inner = type_name[:-2] if type_name.endswith("[]") else type_name
        return [_plain(inner, item) for item in value]
    return value


def encode_args(types: tuple[str, ...], args: list[Any]) -> bytes:
    if len(types) != len(args):
        raise DecodeError(f"Expected {len(types)} arguments, got {len(args)}.")
    return encode(list(types), [_normalise(t, a) for t, a in zip(types, args, strict=True)])


def encode_call(artifact: Artifact, function: str, args: list[Any]) -> bytes:
    abi = artifact.function(function)
    return abi.selector + encode_args(abi.input_types, args)


def decode_result(artifact: Artifact, function: str, data: bytes) -> tuple[Any, ...]:
    abi = artifact.function(function)
    if not abi.output_types:
        return ()
    values = decode(list(abi.output_types), data)
    return tuple(_plain(t, v) for t, v in zip(abi.output_types, values, strict=True))


def decode_event(
    artifact: Artifact, topics: list[bytes], data: bytes
) -> tuple[EventAbi, dict[str, Any]] | None:
    """Decode one log. Returns None for an event this contract does not declare."""
    if not topics:
        return None
    event = artifact.events.get(topics[0].hex())
    if event is None:
        return None
    values: dict[str, Any] = {}
    indexed = iter(topics[1:])
    plain_inputs = [i for i in event.inputs if not i.indexed]
    plain_values = decode([i.type for i in plain_inputs], data) if plain_inputs else ()
    plain_iter = iter(plain_values)
    for item in event.inputs:
        raw = decode([item.type], next(indexed))[0] if item.indexed else next(plain_iter)
        values[item.name] = _plain(item.type, raw)
    return event, values


def revert_reason(output: bytes) -> str:
    """The require() text inside a revert's output, or REVERTED if there is none. Never raises."""
    if output[:4] == ERROR_SELECTOR and len(output) >= 4 + 32:
        try:
            return str(decode(["string"], output[4:])[0])
        except Exception:  # a malformed reason must not hide the revert itself
            return "REVERTED"
    return "REVERTED"
