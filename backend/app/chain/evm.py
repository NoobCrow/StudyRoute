"""SandboxChain: an in-memory EVM (py-evm, the Ethereum Foundation's Python implementation) that
runs the committed contracts.

It is a simulation for the sandbox. There is no network, no peers and no real tokens, and no key
ever exists: a "wallet" is just an address derived from a label, and the server acts as each
party only after the human behind that party has been authorised (with MFA, in the domain layer).
Messages run directly in the EVM, so there are no signed transactions and no gas is charged.
Every transaction is its own block, so the chain's history is easy to replay and to explain.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from eth import constants
from eth._utils.address import generate_contract_address  # pinned version: py-evm 0.12.1b1
from eth.abc import ComputationAPI
from eth.db.atomic import AtomicDB
from eth.vm.execution_context import ExecutionContext
from eth.vm.forks.paris.state import ParisState
from eth.vm.message import Message

from app.chain import codec
from app.chain.artifacts import Artifact, load

GAS_LIMIT = 30_000_000
CHAIN_ID = 1337  # a private sandbox id; it is not registered anywhere
_WALLET_PREFIX = b"studyroute-sandbox-wallet|"


class ChainRevert(Exception):
    """The contract refused the transaction. `reason` is its require() text."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UnknownContract(KeyError):
    pass


@dataclass(frozen=True)
class ChainEvent:
    contract: str
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class Receipt:
    block: int
    timestamp: int
    contract: str
    function: str
    events: tuple[ChainEvent, ...]
    output: tuple[Any, ...]
    gas_used: int


@dataclass(frozen=True)
class Deployed:
    label: str
    artifact: Artifact
    address: str


def wallet_address(label: str) -> str:
    """A sandbox wallet: the last 20 bytes of SHA-256 over a fixed prefix and the label."""
    digest = hashlib.sha256(_WALLET_PREFIX + label.encode("utf-8")).digest()
    return "0x" + digest[-20:].hex()


def _raw(address: str) -> bytes:
    return bytes.fromhex(codec.to_address(address)[2:])


def _failure(computation: ComputationAPI) -> ChainRevert:
    """The reason a computation failed: a require() text, or the kind of EVM halt."""
    if type(computation.error).__name__ == "Revert":
        return ChainRevert(codec.revert_reason(bytes(computation.output)))
    return ChainRevert(f"EVM_HALT_{type(computation.error).__name__.upper()}")


class SandboxChain:
    def __init__(self) -> None:
        self._db = AtomicDB()
        self._root = constants.BLANK_ROOT_HASH
        self._by_label: dict[str, Deployed] = {}
        self._by_address: dict[str, Deployed] = {}
        self.block = 0
        self.timestamp = 0

    # --- reading ---------------------------------------------------------------------------
    def has(self, label: str) -> bool:
        return label in self._by_label

    def deployed(self, label: str) -> Deployed:
        try:
            return self._by_label[label]
        except KeyError as exc:
            raise UnknownContract(label) from exc

    def labels(self) -> list[str]:
        return list(self._by_label)

    def call(
        self, label: str, function: str, args: list[Any], caller: str = "bank"
    ) -> tuple[Any, ...]:
        """A read-only call at the newest block. Changes nothing."""
        target = self.deployed(label)
        state = self._state(self.block, self.timestamp)
        data = codec.encode_call(target.artifact, function, args)
        computation = self._run(
            state, _raw(wallet_address(caller)), _raw(target.address), data, static=True
        )
        if computation.is_error:
            raise _failure(computation)
        return codec.decode_result(target.artifact, function, bytes(computation.output))

    # --- writing ---------------------------------------------------------------------------
    def deploy(
        self, label: str, contract: str, args: list[Any], caller: str, timestamp: int
    ) -> Deployed:
        if label in self._by_label:
            raise ValueError(f"{label} is already deployed")
        artifact = load(contract)
        code = artifact.bytecode + codec.encode_args(artifact.constructor_types, args)
        block, moment = self._next(timestamp)
        state = self._state(block, moment)
        sender = _raw(wallet_address(caller))
        created = generate_contract_address(sender, state.get_nonce(sender))
        state.increment_nonce(sender)
        message = Message(
            gas=GAS_LIMIT, to=constants.CREATE_CONTRACT_ADDRESS, sender=sender, value=0,
            data=b"", code=code, create_address=created,
        )  # fmt: skip
        transaction = state.transaction_context_class(gas_price=0, origin=sender)
        computation = state.computation_class.apply_create_message(state, message, transaction)
        if computation.is_error:
            raise _failure(computation)
        self._commit(state, block, moment)
        deployed = Deployed(label, artifact, "0x" + created.hex())
        self._by_label[label] = deployed
        self._by_address[deployed.address] = deployed
        return deployed

    def send(
        self, label: str, function: str, args: list[Any], caller: str, timestamp: int
    ) -> Receipt:
        """One transaction, one block. A revert changes nothing, not even the block number."""
        target = self.deployed(label)
        data = codec.encode_call(target.artifact, function, args)
        block, moment = self._next(timestamp)
        state = self._state(block, moment)
        computation = self._run(
            state, _raw(wallet_address(caller)), _raw(target.address), data, static=False
        )
        if computation.is_error:
            raise _failure(computation)
        events = self._decode_logs(computation.get_log_entries())
        output = codec.decode_result(target.artifact, function, bytes(computation.output))
        self._commit(state, block, moment)
        return Receipt(
            block=block,
            timestamp=moment,
            contract=label,
            function=function,
            events=events,
            output=output,
            gas_used=int(computation.get_gas_used()),
        )

    def advance(self, timestamp: int) -> int:
        """Move chain time forward (a sandbox control). Returns the new chain time."""
        self.timestamp = max(self.timestamp, timestamp)
        return self.timestamp

    # --- internals -------------------------------------------------------------------------
    def _next(self, timestamp: int) -> tuple[int, int]:
        return self.block + 1, max(int(timestamp), self.timestamp)

    def _state(self, number: int, timestamp: int) -> ParisState:
        context = ExecutionContext(
            coinbase=constants.ZERO_ADDRESS,
            timestamp=timestamp,
            block_number=number,
            difficulty=0,
            mix_hash=constants.ZERO_HASH32,
            gas_limit=GAS_LIMIT,
            prev_hashes=[],
            chain_id=CHAIN_ID,
            base_fee_per_gas=0,
        )
        return ParisState(self._db, context, self._root)

    def _run(
        self, state: ParisState, sender: bytes, to: bytes, data: bytes, *, static: bool
    ) -> ComputationAPI:
        message = Message(
            gas=GAS_LIMIT, to=to, sender=sender, value=0, data=data, code=state.get_code(to),
            is_static=static,
        )  # fmt: skip
        transaction = state.transaction_context_class(gas_price=0, origin=sender)
        return state.computation_class.apply_message(state, message, transaction)

    def _commit(self, state: ParisState, block: int, timestamp: int) -> None:
        state.persist()
        self._root = state.state_root
        self.block, self.timestamp = block, timestamp

    def _decode_logs(self, logs: Any) -> tuple[ChainEvent, ...]:
        found: list[ChainEvent] = []
        for address, topics, data in logs:
            target = self._by_address.get("0x" + bytes(address).hex())
            if target is None:
                continue
            topic_bytes = [int(topic).to_bytes(32, "big") for topic in topics]
            decoded = codec.decode_event(target.artifact, topic_bytes, bytes(data))
            if decoded is not None:
                event, values = decoded
                found.append(ChainEvent(target.label, event.name, values))
        return tuple(found)
