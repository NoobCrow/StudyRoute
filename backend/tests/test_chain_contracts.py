"""The three Solidity contracts, run for real on the in-memory EVM.

These are the contract tests: access control, who may move funds and when, the compliance
freeze, and the rule that the escrow always holds exactly what is still locked.
"""

from __future__ import annotations

import hashlib
import random

import pytest
from eth_abi import encode

from app.chain import codec
from app.chain.artifacts import ARTIFACT_DIR, CONTRACT_NAMES, load
from app.chain.evm import ChainRevert, SandboxChain, wallet_address

T0 = 1_800_000_000
DAY = 86_400
REF = "0x" + hashlib.sha256(b"INV-2026-4471").hexdigest()


class Rig:
    """A chain with the bank, a compliance officer, a payer, a university and a stranger."""

    def __init__(self) -> None:
        self.chain = SandboxChain()
        self.clock = T0
        self.chain.deploy(
            "token",
            "TokenisedDeposit",
            ["Tokenised deposit GBP (sandbox)", "tGBP", 2, wallet_address("bank")],
            "bank",
            self.clock,
        )
        self.chain.deploy(
            "escrow", "TuitionEscrow", [wallet_address("compliance")], "bank", self.clock
        )
        self.chain.deploy("anchor", "AuditAnchor", [wallet_address("bank")], "bank", self.clock)

    def send(self, contract: str, function: str, args: list, caller: str):
        return self.chain.send(contract, function, args, caller, self.clock)

    def view(self, contract: str, function: str, args: list):
        return self.chain.call(contract, function, args)

    def refused(self, contract: str, function: str, args: list, caller: str) -> str:
        with pytest.raises(ChainRevert) as caught:
            self.send(contract, function, args, caller)
        return caught.value.reason

    def balance(self, who: str) -> int:
        return int(self.view("token", "balanceOf", [wallet_address(who)])[0])

    def escrow_balance(self) -> int:
        return int(self.view("token", "balanceOf", [self.chain.deployed("escrow").address])[0])

    def fund(self, who: str, amount: int) -> None:
        self.send("token", "mint", [wallet_address(who), amount], "bank")

    def open(self, amounts: list[int], days: list[int], payer: str = "payer") -> int:
        """Fund the payer, approve the escrow, create the escrow. Returns its id."""
        self.fund(payer, sum(amounts))
        self.send("token", "approve", [self.chain.deployed("escrow").address, sum(amounts)], payer)
        receipt = self.send(
            "escrow", "create",
            [self.chain.deployed("token").address, wallet_address("uni"), REF, amounts, [T0 + d * DAY for d in days]],
            payer,
        )  # fmt: skip
        return int(receipt.events[-1].args["id"])

    def status(self, escrow_id: int) -> int:
        return int(self.view("escrow", "getEscrow", [escrow_id])[4])

    def tranche_states(self, escrow_id: int) -> list[int]:
        count = int(self.view("escrow", "getEscrow", [escrow_id])[7])
        return [int(self.view("escrow", "getTranche", [escrow_id, i])[2]) for i in range(count)]

    def locked(self, escrow_id: int) -> int:
        return int(self.view("escrow", "getEscrow", [escrow_id])[5])


def event(receipt, name: str):
    """The escrow's own event by name (a payout also emits the token's Transfer first)."""
    return next(e for e in receipt.events if e.name == name)


ACTIVE, FROZEN, COMPLETED, CANCELLED = 1, 2, 3, 4
LOCKED, RELEASED, REFUNDED = 0, 1, 2


@pytest.fixture
def rig() -> Rig:
    return Rig()


# --- the artifacts ----------------------------------------------------------------------------
def test_every_artifact_matches_its_source_file() -> None:
    """A contract that changed but was not rebuilt (npm run build in contracts/) fails here."""
    root = ARTIFACT_DIR.parents[3]
    for name in CONTRACT_NAMES:
        artifact = load(name)
        source = (root / artifact.source_file).read_bytes()
        assert hashlib.sha256(source).hexdigest() == artifact.source_sha256, f"{name} is stale"
        assert artifact.solc.startswith("0.8."), artifact.solc


def test_selectors_and_topics_are_the_well_known_ones() -> None:
    token = load("TokenisedDeposit")
    assert (
        token.function("transfer").selector.hex() == "a9059cbb"
    )  # ERC-20 transfer(address,uint256)
    assert token.function("balanceOf").selector.hex() == "70a08231"
    assert token.function("approve").selector.hex() == "095ea7b3"
    transfer_topic = "ddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    assert transfer_topic in token.events and token.events[transfer_topic].name == "Transfer"


# --- the tokenised deposit --------------------------------------------------------------------
def test_only_the_issuing_bank_can_mint(rig: Rig) -> None:
    assert rig.refused("token", "mint", [wallet_address("payer"), 5], "payer") == "ONLY_ISSUER"
    rig.fund("payer", 1_000)
    assert rig.balance("payer") == 1_000 and rig.view("token", "totalSupply", []) == (1_000,)


def test_transfers_need_balance_and_allowance(rig: Rig) -> None:
    rig.fund("payer", 100)
    assert (
        rig.refused("token", "transfer", [wallet_address("uni"), 101], "payer")
        == "INSUFFICIENT_BALANCE"
    )
    assert (
        rig.refused(
            "token", "transferFrom", [wallet_address("payer"), wallet_address("uni"), 1], "uni"
        )
        == "INSUFFICIENT_ALLOWANCE"
    )
    rig.send("token", "transfer", [wallet_address("uni"), 40], "payer")
    assert (rig.balance("payer"), rig.balance("uni")) == (60, 40)


def test_redeeming_burns_and_cannot_overdraw(rig: Rig) -> None:
    rig.fund("payer", 100)
    rig.send("token", "redeem", [30], "payer")
    assert rig.balance("payer") == 70 and rig.view("token", "totalSupply", []) == (70,)
    assert rig.refused("token", "redeem", [71], "payer") == "INSUFFICIENT_BALANCE"


# --- creating an escrow -----------------------------------------------------------------------
def test_creating_an_escrow_locks_exactly_the_total(rig: Rig) -> None:
    escrow_id = rig.open([400, 300, 300], [10, 40, 70])
    assert escrow_id == 1
    assert rig.escrow_balance() == 1_000 and rig.balance("payer") == 0
    payer, beneficiary, _token, ref, status, locked, refunded, count = rig.view(
        "escrow", "getEscrow", [escrow_id]
    )
    assert (payer, beneficiary) == (wallet_address("payer"), wallet_address("uni"))
    assert (ref, status, locked, refunded, count) == (REF, ACTIVE, 1_000, 0, 3)
    assert rig.view("escrow", "getTranche", [escrow_id, 1]) == (300, T0 + 40 * DAY, LOCKED)


def test_create_event_carries_the_terms(rig: Rig) -> None:
    rig.fund("payer", 500)
    rig.send("token", "approve", [rig.chain.deployed("escrow").address, 500], "payer")
    receipt = rig.send(
        "escrow",
        "create",
        [rig.chain.deployed("token").address, wallet_address("uni"), REF, [500], [T0 + DAY]],
        "payer",
    )
    created = next(e for e in receipt.events if e.name == "Created")
    assert created.args["total"] == 500 and created.args["tranches"] == 1
    assert created.args["payer"] == wallet_address("payer") and created.args[
        "beneficiary"
    ] == wallet_address("uni")


@pytest.mark.parametrize(
    ("amounts", "dates", "reason"),
    [
        ([], [], "BAD_TRANCHE_COUNT"),
        ([1] * 61, [T0] * 61, "BAD_TRANCHE_COUNT"),
        ([10, 20], [T0], "LENGTH_MISMATCH"),
        ([10, 0], [T0, T0 + 1], "ZERO_AMOUNT"),
        ([10, 20], [T0 + 5, T0 + 4], "DATES_NOT_ORDERED"),
    ],
)
def test_create_rejects_bad_terms(
    rig: Rig, amounts: list[int], dates: list[int], reason: str
) -> None:
    rig.fund("payer", 1_000)
    rig.send("token", "approve", [rig.chain.deployed("escrow").address, 1_000], "payer")
    args = [rig.chain.deployed("token").address, wallet_address("uni"), REF, amounts, dates]
    assert rig.refused("escrow", "create", args, "payer") == reason
    assert rig.escrow_balance() == 0, "a refused escrow locks nothing"


def test_create_needs_funds_and_allowance_and_a_different_beneficiary(rig: Rig) -> None:
    token = rig.chain.deployed("token").address
    args = [token, wallet_address("uni"), REF, [100], [T0]]
    assert rig.refused("escrow", "create", args, "payer") == "INSUFFICIENT_ALLOWANCE"
    rig.send("token", "approve", [rig.chain.deployed("escrow").address, 100], "payer")
    assert rig.refused("escrow", "create", args, "payer") == "INSUFFICIENT_BALANCE"
    rig.fund("payer", 100)
    own = [token, wallet_address("payer"), REF, [100], [T0]]
    assert rig.refused("escrow", "create", own, "payer") == "PAYER_IS_BENEFICIARY"


# --- releasing --------------------------------------------------------------------------------
def test_a_tranche_cannot_be_released_before_its_date_but_can_after(rig: Rig) -> None:
    escrow_id = rig.open([600, 400], [10, 40])
    assert rig.refused("escrow", "releaseDue", [escrow_id, 0], "uni") == "NOT_DUE"
    rig.clock = T0 + 10 * DAY
    receipt = rig.send("escrow", "releaseDue", [escrow_id, 0], "uni")
    released = event(receipt, "Released")
    assert released.args["amount"] == 600 and released.args["early"] is False
    assert (rig.balance("uni"), rig.escrow_balance(), rig.locked(escrow_id)) == (600, 400, 400)
    assert rig.status(escrow_id) == ACTIVE and rig.tranche_states(escrow_id) == [RELEASED, LOCKED]


def test_only_a_party_can_release_and_a_tranche_pays_once(rig: Rig) -> None:
    escrow_id = rig.open([500], [1])
    rig.clock = T0 + 2 * DAY
    assert rig.refused("escrow", "releaseDue", [escrow_id, 0], "stranger") == "NOT_A_PARTY"
    rig.send("escrow", "releaseDue", [escrow_id, 0], "payer")
    assert rig.status(escrow_id) == COMPLETED
    assert rig.refused("escrow", "releaseDue", [escrow_id, 0], "uni") == "NOT_ACTIVE"


def test_only_the_payer_can_release_early(rig: Rig) -> None:
    escrow_id = rig.open([500, 500], [30, 60])
    assert rig.refused("escrow", "releaseEarly", [escrow_id, 0], "uni") == "ONLY_PAYER"
    assert rig.refused("escrow", "releaseEarly", [escrow_id, 0], "compliance") == "ONLY_PAYER"
    receipt = rig.send("escrow", "releaseEarly", [escrow_id, 1], "payer")
    assert event(receipt, "Released").args["early"] is True
    assert rig.balance("uni") == 500 and rig.tranche_states(escrow_id) == [LOCKED, RELEASED]
    assert rig.refused("escrow", "releaseEarly", [escrow_id, 1], "payer") == "NOT_LOCKED"


def test_releasing_the_last_tranche_completes_the_escrow(rig: Rig) -> None:
    escrow_id = rig.open([100, 200], [0, 0])
    rig.send("escrow", "releaseDue", [escrow_id, 0], "uni")
    receipt = rig.send("escrow", "releaseDue", [escrow_id, 1], "uni")
    assert [e.name for e in receipt.events] == ["Transfer", "Released", "Finished"]
    assert event(receipt, "Finished").args["status"] == COMPLETED
    assert (
        rig.status(escrow_id) == COMPLETED
        and rig.escrow_balance() == 0
        and rig.balance("uni") == 300
    )


# --- taking it back ---------------------------------------------------------------------------
def test_cancel_returns_only_tranches_that_are_not_yet_due(rig: Rig) -> None:
    escrow_id = rig.open([100, 100, 100], [10, 40, 70])
    rig.clock = T0 + 10 * DAY  # tranche 0 is due, 1 and 2 are not
    receipt = rig.send("escrow", "cancel", [escrow_id], "payer")
    assert next(e for e in receipt.events if e.name == "Cancelled").args["refunded"] == 200
    assert rig.balance("payer") == 200 and rig.escrow_balance() == 100
    assert rig.tranche_states(escrow_id) == [LOCKED, REFUNDED, REFUNDED]
    assert rig.status(escrow_id) == ACTIVE, "the due tranche is still the university's"
    rig.send("escrow", "releaseDue", [escrow_id, 0], "uni")
    assert rig.status(escrow_id) == CANCELLED and rig.balance("uni") == 100


def test_cancel_is_for_the_payer_and_needs_something_to_cancel(rig: Rig) -> None:
    escrow_id = rig.open([100], [10])
    assert rig.refused("escrow", "cancel", [escrow_id], "uni") == "ONLY_PAYER"
    assert rig.refused("escrow", "cancel", [escrow_id], "stranger") == "ONLY_PAYER"
    rig.clock = T0 + 11 * DAY
    assert rig.refused("escrow", "cancel", [escrow_id], "payer") == "NOTHING_TO_CANCEL"


def test_the_university_can_send_a_tranche_back_after_a_refused_visa(rig: Rig) -> None:
    escrow_id = rig.open([700, 300], [10, 40])
    assert rig.refused("escrow", "refund", [escrow_id, 0], "payer") == "ONLY_BENEFICIARY"
    rig.send("escrow", "refund", [escrow_id, 0], "uni")
    rig.send("escrow", "refund", [escrow_id, 1], "uni")
    assert (
        rig.balance("payer") == 1_000
        and rig.escrow_balance() == 0
        and rig.status(escrow_id) == CANCELLED
    )


# --- compliance --------------------------------------------------------------------------------
def test_compliance_can_freeze_and_unfreeze_but_nobody_else_can(rig: Rig) -> None:
    escrow_id = rig.open([100], [0])
    why = "0x" + hashlib.sha256(b"sanctions screening hit").hexdigest()
    for outsider in ("payer", "uni", "stranger"):
        assert rig.refused("escrow", "freeze", [escrow_id, why], outsider) == "ONLY_COMPLIANCE"
    receipt = rig.send("escrow", "freeze", [escrow_id, why], "compliance")
    assert receipt.events[0].name == "Frozen" and receipt.events[0].args["reason"] == why
    assert rig.status(escrow_id) == FROZEN
    assert rig.refused("escrow", "freeze", [escrow_id, why], "compliance") == "NOT_ACTIVE"
    assert rig.refused("escrow", "unfreeze", [escrow_id], "payer") == "ONLY_COMPLIANCE"
    rig.send("escrow", "unfreeze", [escrow_id], "compliance")
    assert rig.status(escrow_id) == ACTIVE


def test_a_frozen_escrow_moves_nothing_for_anyone(rig: Rig) -> None:
    escrow_id = rig.open([100, 100], [0, 60])
    rig.send("escrow", "freeze", [escrow_id, "0x" + "00" * 31 + "01"], "compliance")
    rig.clock = T0 + DAY
    for function, args, caller in (
        ("releaseDue", [escrow_id, 0], "uni"),
        ("releaseEarly", [escrow_id, 1], "payer"),
        ("refund", [escrow_id, 1], "uni"),
        ("cancel", [escrow_id], "payer"),
    ):
        assert rig.refused("escrow", function, args, caller) == "NOT_ACTIVE", function
    assert rig.escrow_balance() == 200 and rig.balance("uni") == 0 and rig.balance("payer") == 0


def test_compliance_has_no_way_to_move_funds(rig: Rig) -> None:
    escrow_id = rig.open([100], [0])
    rig.clock = T0 + DAY
    for function, args in (
        ("releaseDue", [escrow_id, 0]),
        ("releaseEarly", [escrow_id, 0]),
        ("refund", [escrow_id, 0]),
        ("cancel", [escrow_id]),
    ):
        reason = rig.refused("escrow", function, args, "compliance")
        assert reason in {"NOT_A_PARTY", "ONLY_PAYER", "ONLY_BENEFICIARY"}, (function, reason)
    assert rig.escrow_balance() == 100 and rig.balance("compliance") == 0


def test_unknown_escrows_and_tranches_are_refused(rig: Rig) -> None:
    assert rig.refused("escrow", "releaseDue", [99, 0], "payer") == "NO_SUCH_ESCROW"
    escrow_id = rig.open([100], [0])
    assert rig.refused("escrow", "releaseDue", [escrow_id, 5], "payer") == "NO_SUCH_TRANCHE"
    with pytest.raises(ChainRevert, match="NO_SUCH_ESCROW"):
        rig.view("escrow", "getEscrow", [42])


# --- the invariant, under random use -----------------------------------------------------------
def test_the_escrow_always_holds_exactly_what_is_still_locked() -> None:
    """Random creates, releases, refunds, cancels and freezes: money is never created or lost."""
    rng = random.Random(20261015)
    rig = Rig()
    ids: list[int] = []
    minted = 0
    for _ in range(300):
        action = rng.choice(
            ["open", "open", "advance", "due", "early", "refund", "cancel", "freeze", "unfreeze"]
        )
        try:
            if action == "open" or not ids:
                n = rng.randint(1, 4)
                amounts = [rng.randint(1, 5_000) for _ in range(n)]
                days = sorted(rng.randint(0, 120) for _ in range(n))
                ids.append(rig.open(amounts, days))
                minted += sum(amounts)
            elif action == "advance":
                rig.clock += rng.randint(1, 20) * DAY
            else:
                escrow_id = rng.choice(ids)
                tranche = rng.randint(0, 3)
                call = {
                    "due": ("releaseDue", [escrow_id, tranche], rng.choice(["payer", "uni"])),
                    "early": ("releaseEarly", [escrow_id, tranche], "payer"),
                    "refund": ("refund", [escrow_id, tranche], "uni"),
                    "cancel": ("cancel", [escrow_id], "payer"),
                    "freeze": ("freeze", [escrow_id, "0x" + "ab" * 32], "compliance"),
                    "unfreeze": ("unfreeze", [escrow_id], "compliance"),
                }[action]
                rig.send("escrow", call[0], call[1], call[2])
        except ChainRevert:
            pass  # a refused move must change nothing, which the checks below prove
        locked = sum(rig.locked(i) for i in ids)
        assert rig.escrow_balance() == locked
        total = rig.balance("payer") + rig.balance("uni") + rig.escrow_balance()
        assert total == minted == rig.view("token", "totalSupply", [])[0]


# --- the audit anchor -------------------------------------------------------------------------
def test_only_the_operator_can_anchor_and_anchors_only_move_forward(rig: Rig) -> None:
    head = "0x" + hashlib.sha256(b"head 7").hexdigest()
    assert rig.refused("anchor", "anchor", [7, head], "stranger") == "ONLY_OPERATOR"
    assert rig.refused("anchor", "anchor", [7, "0x" + "00" * 32], "bank") == "EMPTY_HEAD"
    receipt = rig.send("anchor", "anchor", [7, head], "bank")
    assert receipt.events[0].name == "Anchored" and receipt.events[0].args["seq"] == 7
    assert rig.refused("anchor", "anchor", [7, head], "bank") == "SEQ_NOT_INCREASING"
    assert rig.refused("anchor", "anchor", [3, head], "bank") == "SEQ_NOT_INCREASING"
    rig.send("anchor", "anchor", [9, "0x" + hashlib.sha256(b"head 9").hexdigest()], "bank")
    assert rig.view("anchor", "count", []) == (2,)
    assert rig.view("anchor", "get", [0]) == (7, T0, head)
    with pytest.raises(ChainRevert, match="NO_SUCH_ANCHOR"):
        rig.view("anchor", "get", [5])


# --- the chain itself ----------------------------------------------------------------------------
def test_a_refused_transaction_changes_nothing_not_even_the_block_number(rig: Rig) -> None:
    before = (rig.chain.block, rig.chain.timestamp)
    rig.refused("token", "mint", [wallet_address("payer"), 1], "payer")
    assert (rig.chain.block, rig.chain.timestamp) == before


def test_replaying_the_same_transactions_gives_the_same_chain() -> None:
    def build() -> tuple[Rig, int]:
        rig = Rig()
        escrow_id = rig.open([250, 250], [5, 50])
        rig.clock = T0 + 6 * DAY
        rig.send("escrow", "releaseDue", [escrow_id, 0], "uni")
        return rig, escrow_id

    first, escrow_id = build()
    second, _ = build()
    for label in ("token", "escrow", "anchor"):
        assert first.chain.deployed(label).address == second.chain.deployed(label).address
    assert (first.chain.block, first.chain.timestamp) == (
        second.chain.block,
        second.chain.timestamp,
    )
    assert first.view("escrow", "getEscrow", [escrow_id]) == second.view(
        "escrow", "getEscrow", [escrow_id]
    )


def test_chain_time_never_goes_backwards(rig: Rig) -> None:
    rig.clock = T0 + 5 * DAY
    rig.fund("payer", 1)
    stamp = rig.chain.timestamp
    rig.clock = T0  # the server clock jumped back
    rig.fund("payer", 1)
    assert rig.chain.timestamp == stamp


def test_codec_round_trips_and_reads_revert_reasons() -> None:
    token = load("TokenisedDeposit")
    data = codec.encode_call(token, "transfer", [wallet_address("uni"), 1234])
    assert data[:4].hex() == "a9059cbb" and len(data) == 4 + 64
    with pytest.raises(codec.DecodeError):
        codec.encode_call(token, "transfer", [wallet_address("uni")])
    reason = codec.ERROR_SELECTOR + encode(["string"], ["NOT_DUE"])
    assert codec.revert_reason(reason) == "NOT_DUE"
    assert codec.revert_reason(b"") == "REVERTED"
    assert codec.revert_reason(codec.ERROR_SELECTOR + b"") == "REVERTED"
