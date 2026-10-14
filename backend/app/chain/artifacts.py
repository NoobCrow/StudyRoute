"""Compiled contract artifacts. Built by contracts/build.mjs and committed, so the backend never
needs Node or a Solidity compiler. test_chain_artifacts.py checks each one against its source."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
CONTRACT_NAMES = ("TokenisedDeposit", "TuitionEscrow", "AuditAnchor")


@dataclass(frozen=True)
class FunctionAbi:
    name: str
    signature: str
    selector: bytes
    input_types: tuple[str, ...]
    output_types: tuple[str, ...]


@dataclass(frozen=True)
class EventInput:
    name: str
    type: str
    indexed: bool


@dataclass(frozen=True)
class EventAbi:
    name: str
    signature: str
    topic0: str
    inputs: tuple[EventInput, ...]


@dataclass(frozen=True)
class Artifact:
    name: str
    solc: str
    source_file: str
    source_sha256: str
    bytecode: bytes
    functions: dict[str, FunctionAbi]
    events: dict[str, EventAbi]  # keyed by topic0 (lower case hex, no 0x)
    constructor_types: tuple[str, ...]

    def function(self, name: str) -> FunctionAbi:
        try:
            return self.functions[name]
        except KeyError as exc:
            raise KeyError(f"{self.name} has no function {name}") from exc


def _types(items: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(item["type"]) for item in items)


def _parse(raw: dict[str, Any]) -> Artifact:
    functions: dict[str, FunctionAbi] = {}
    events: dict[str, EventAbi] = {}
    constructor: tuple[str, ...] = ()
    for item in raw["abi"]:
        kind = item["type"]
        if kind == "constructor":
            constructor = _types(item["inputs"])
        elif kind == "function":
            signature = f"{item['name']}({','.join(_types(item['inputs']))})"
            functions[item["name"]] = FunctionAbi(
                name=item["name"],
                signature=signature,
                selector=bytes.fromhex(raw["selectors"][signature]),
                input_types=_types(item["inputs"]),
                output_types=_types(item["outputs"]),
            )
        elif kind == "event":
            signature = f"{item['name']}({','.join(_types(item['inputs']))})"
            topic0 = raw["events"][signature]
            events[topic0] = EventAbi(
                name=item["name"],
                signature=signature,
                topic0=topic0,
                inputs=tuple(
                    EventInput(i["name"], i["type"], i["indexed"]) for i in item["inputs"]
                ),
            )
    return Artifact(
        name=raw["contract"],
        solc=raw["solc"],
        source_file=raw["sourceFile"],
        source_sha256=raw["sourceSha256"],
        bytecode=bytes.fromhex(raw["bytecode"]),
        functions=functions,
        events=events,
        constructor_types=constructor,
    )


@cache
def load(name: str) -> Artifact:
    raw = json.loads((ARTIFACT_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return _parse(raw)
