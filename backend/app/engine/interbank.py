"""Interbank engine for the sandbox bank network. Pure code: no clock, no database, no network.

It turns a transfer request into a *plan*: the journals each bank will post, in order, with the
delay before each step. Nothing here moves money; the domain posts the journals to the ledger.

Bookkeeping is double entry. A journal is a list of debits and credits, and for every currency
the debits equal the credits. Accounts keep a balance on their normal side (a customer deposit
is a credit-normal liability, a nostro is a debit-normal asset), so a debit lowers a customer
balance and raises a nostro balance.

Two kinds of transfer are planned:

* national: inside one country and one currency, over a rail (same bank, instant, next batch or
  high value). Money passes through the sender's reserve at a clearing house to the receiver's.
* international: from a Bangladesh bank in BDT to a host-country bank in the target currency.
  The originating bank sells the foreign currency, pays it out of its nostro account at a
  correspondent, the correspondent forwards it through its own nostro at the beneficiary's bank,
  and the beneficiary's bank credits the customer. Pricing and the charge code come straight
  from the fee engine (`engine.quote`), so the numbers equal the ones on the Compare screen.

Every bank, rate, fee and limit is invented; see config/bank_network.yaml.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from app.core.crypto import hash_object
from app.engine.money import EngineError, Money, round_half_up
from app.engine.quote import ChargeCode, ProviderResult

BDT = "BDT"
ON_US = "ON_US"
SWIFT = "SWIFT"


class RailRejected(EngineError):
    """The transfer cannot use the chosen rail or route. `code` is a stable machine reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Side(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

    @property
    def opposite(self) -> Side:
        return Side.CREDIT if self is Side.DEBIT else Side.DEBIT


class AccountKind(StrEnum):
    CUSTOMER = "CUSTOMER"  # a customer's deposit account (liability, credit-normal)
    IN_FLIGHT = "IN_FLIGHT"  # money taken from a customer and not yet sent on (liability)
    FEE_INCOME = "FEE_INCOME"  # fees the bank has earned (income, credit-normal)
    CASH = "CASH"  # the bank's own cash, the other side of opening balances (asset)
    FX_POSITION = "FX_POSITION"  # foreign-exchange position in one currency (asset, may go short)
    NOSTRO = "NOSTRO"  # "our account at your bank": an asset, mirrors a VOSTRO
    VOSTRO = "VOSTRO"  # "your account at our bank": a liability, mirrors a NOSTRO
    RESERVE = "RESERVE"  # a bank's settlement reserve at a clearing house (asset)
    CLEARING = "CLEARING"  # the clearing house's liability to one bank, mirrors a RESERVE


NORMAL_SIDE: dict[AccountKind, Side] = {
    AccountKind.CUSTOMER: Side.CREDIT,
    AccountKind.IN_FLIGHT: Side.CREDIT,
    AccountKind.FEE_INCOME: Side.CREDIT,
    AccountKind.CASH: Side.DEBIT,
    AccountKind.FX_POSITION: Side.DEBIT,
    AccountKind.NOSTRO: Side.DEBIT,
    AccountKind.VOSTRO: Side.CREDIT,
    AccountKind.RESERVE: Side.DEBIT,
    AccountKind.CLEARING: Side.CREDIT,
}
ALLOWS_NEGATIVE = frozenset({AccountKind.CASH, AccountKind.FX_POSITION})

# (asset account kind, the liability kind that must show the same balance at the other bank)
MIRROR_KINDS: dict[AccountKind, AccountKind] = {
    AccountKind.NOSTRO: AccountKind.VOSTRO,
    AccountKind.VOSTRO: AccountKind.NOSTRO,
    AccountKind.RESERVE: AccountKind.CLEARING,
    AccountKind.CLEARING: AccountKind.RESERVE,
}


@dataclass(frozen=True)
class AccountRef:
    """Names a ledger account without needing the database."""

    bank: str
    kind: AccountKind
    currency: str
    counterparty: str = ""  # NOSTRO/VOSTRO/RESERVE/CLEARING: the institution on the other side
    number: str = ""  # CUSTOMER only

    def to_dict(self) -> dict[str, str]:
        return {
            "bank": self.bank,
            "kind": self.kind.value,
            "currency": self.currency,
            "counterparty": self.counterparty,
            "number": self.number,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AccountRef:
        return cls(
            bank=str(data["bank"]),
            kind=AccountKind(data["kind"]),
            currency=str(data["currency"]),
            counterparty=str(data.get("counterparty", "")),
            number=str(data.get("number", "")),
        )

    def mirror(self) -> AccountRef | None:
        """The same relationship seen from the other institution, or None for plain accounts."""
        kind = MIRROR_KINDS.get(self.kind)
        if kind is None:
            return None
        return AccountRef(self.counterparty, kind, self.currency, self.bank)


@dataclass(frozen=True)
class Posting:
    account: AccountRef
    side: Side
    amount_minor: int

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise TypeError("posting amounts are integer minor units")
        if self.amount_minor <= 0:
            raise ValueError("a posting amount must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "account": self.account.to_dict(),
            "side": self.side.value,
            "amount_minor": self.amount_minor,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Posting:
        return cls(
            AccountRef.from_dict(data["account"]), Side(data["side"]), int(data["amount_minor"])
        )


@dataclass(frozen=True)
class Journal:
    """One balanced posting: for each currency, debits equal credits."""

    memo: str
    postings: tuple[Posting, ...]

    def totals(self) -> dict[str, tuple[int, int]]:
        sums: dict[str, list[int]] = {}
        for posting in self.postings:
            debit_credit = sums.setdefault(posting.account.currency, [0, 0])
            debit_credit[0 if posting.side is Side.DEBIT else 1] += posting.amount_minor
        return {currency: (d, c) for currency, (d, c) in sums.items()}

    def is_balanced(self) -> bool:
        return bool(self.postings) and all(d == c for d, c in self.totals().values())

    def reversed(self) -> Journal:
        """The exact opposite posting, which restores every balance this journal changed."""
        flipped = tuple(Posting(p.account, p.side.opposite, p.amount_minor) for p in self.postings)
        return Journal(f"Reversal: {self.memo}", flipped)

    def to_dict(self) -> dict[str, Any]:
        return {"memo": self.memo, "postings": [p.to_dict() for p in self.postings]}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Journal:
        return cls(str(data["memo"]), tuple(Posting.from_dict(p) for p in data["postings"]))


def make_journal(memo: str, lines: Iterable[tuple[AccountRef, Side, int]]) -> Journal:
    """Build a journal, dropping zero lines (a zero fee posts nothing) and checking the balance."""
    journal = Journal(memo, tuple(Posting(a, s, n) for a, s, n in lines if n != 0))
    if not journal.is_balanced():
        raise ValueError(f"unbalanced journal: {memo}: {journal.totals()}")
    return journal


@dataclass(frozen=True)
class Step:
    """One hop: an institution acts after `delay_seconds` and posts these journals."""

    stage: str
    bank: str
    delay_seconds: int
    summary: str
    journals: tuple[Journal, ...]
    message: str  # the simulated message type that travels with the hop

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "bank": self.bank,
            "delay_seconds": self.delay_seconds,
            "summary": self.summary,
            "journals": [j.to_dict() for j in self.journals],
            "message": self.message,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Step:
        return cls(
            stage=str(data["stage"]),
            bank=str(data["bank"]),
            delay_seconds=int(data["delay_seconds"]),
            summary=str(data["summary"]),
            journals=tuple(Journal.from_dict(j) for j in data["journals"]),
            message=str(data["message"]),
        )


@dataclass(frozen=True)
class TransferPlan:
    kind: Literal["NATIONAL", "INTERNATIONAL"]
    rail: str
    source: AccountRef
    destination: AccountRef
    debit: Money  # everything the payer's account is charged
    credit: Money  # what the beneficiary's account receives
    fee: Money  # the originating bank's charge in the payer's currency
    hold: Journal
    steps: tuple[Step, ...]
    figures: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "rail": self.rail,
            "source": self.source.to_dict(),
            "destination": self.destination.to_dict(),
            "debit": self.debit.to_dict(),
            "credit": self.credit.to_dict(),
            "fee": self.fee.to_dict(),
            "hold": self.hold.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "figures": dict(self.figures),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TransferPlan:
        def money(key: str) -> Money:
            return Money(int(data[key]["amount_minor"]), str(data[key]["currency"]))

        return cls(
            kind=data["kind"],
            rail=str(data["rail"]),
            source=AccountRef.from_dict(data["source"]),
            destination=AccountRef.from_dict(data["destination"]),
            debit=money("debit"),
            credit=money("credit"),
            fee=money("fee"),
            hold=Journal.from_dict(data["hold"]),
            steps=tuple(Step.from_dict(s) for s in data["steps"]),
            figures=dict(data["figures"]),
        )

    @property
    def plan_hash(self) -> str:
        return hash_object(self.to_dict())

    def all_journals(self) -> list[Journal]:
        return [self.hold, *(j for step in self.steps for j in step.journals)]


# --- national ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class RailTerms:
    code: str
    label: str
    currency: str
    fee_fixed_minor: int
    fee_bps: int
    min_minor: int
    max_minor: int | None
    delays: tuple[int, ...]

    def fee_for(self, amount_minor: int) -> int:
        share = round_half_up(Decimal(amount_minor) * self.fee_bps / Decimal(10_000))
        return self.fee_fixed_minor + share

    def check(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise RailRejected("CURRENCY_MISMATCH", f"{self.label} carries {self.currency} only.")
        if amount.amount_minor < self.min_minor:
            minimum = Money(self.min_minor, self.currency).format()
            raise RailRejected("BELOW_RAIL_MINIMUM", f"{self.label} needs at least {minimum}.")
        if self.max_minor is not None and amount.amount_minor > self.max_minor:
            maximum = Money(self.max_minor, self.currency).format()
            raise RailRejected("ABOVE_RAIL_MAXIMUM", f"{self.label} allows at most {maximum}.")


def on_us_terms(currency: str, delays: tuple[int, ...]) -> RailTerms:
    return RailTerms(ON_US, "Same-bank transfer (simulated)", currency, 0, 0, 1, None, delays)


def eligible_rails(rails: Mapping[str, RailTerms], amount: Money) -> list[RailTerms]:
    """Rails that accept this amount, cheapest first, then fastest."""
    found = []
    for terms in rails.values():
        try:
            terms.check(amount)
        except RailRejected:
            continue
        found.append(terms)
    return sorted(found, key=lambda t: (t.fee_for(amount.amount_minor), sum(t.delays), t.code))


def _customer_check(source: AccountRef, destination: AccountRef) -> None:
    if source.kind is not AccountKind.CUSTOMER or destination.kind is not AccountKind.CUSTOMER:
        raise RailRejected("NOT_A_CUSTOMER_ACCOUNT", "Both ends must be customer accounts.")
    if source == destination:
        raise RailRejected("SAME_ACCOUNT", "The source and destination are the same account.")


def plan_national(
    *,
    source: AccountRef,
    destination: AccountRef,
    amount: Money,
    rail: RailTerms,
    clearing_house: str | None,
) -> TransferPlan:
    """Plan a same-currency transfer inside one country."""
    _customer_check(source, destination)
    ccy = amount.currency
    if not (source.currency == destination.currency == ccy):
        raise RailRejected("CURRENCY_MISMATCH", "A national transfer keeps one currency.")
    amount.require_positive()
    rail.check(amount)
    fee_minor = rail.fee_for(amount.amount_minor)
    total = amount.amount_minor + fee_minor
    a, b = source.bank, destination.bank
    in_flight = AccountRef(a, AccountKind.IN_FLIGHT, ccy)
    fee_income = AccountRef(a, AccountKind.FEE_INCOME, ccy)
    hold = make_journal(
        "Funds reserved for transfer",
        [(source, Side.DEBIT, total), (in_flight, Side.CREDIT, total)],
    )
    if rail.code == ON_US:
        if a != b:
            raise RailRejected("NOT_SAME_BANK", "A same-bank transfer needs one bank.")
        steps = (
            Step(
                "CREDIT_BENEFICIARY", a, rail.delays[0], "Bank credits its own customer",
                (
                    make_journal(
                        "Credit beneficiary (same bank)",
                        [
                            (in_flight, Side.DEBIT, total),
                            (fee_income, Side.CREDIT, fee_minor),
                            (destination, Side.CREDIT, amount.amount_minor),
                        ],
                    ),
                ),
                "BOOK_TRANSFER",
            ),
        )  # fmt: skip
    else:
        if a == b or clearing_house is None:
            raise RailRejected(
                "NEEDS_CLEARING", "An interbank rail needs two banks and a clearing house."
            )
        if len(rail.delays) != 3:
            raise ValueError("an interbank rail has three delays")
        reserve_a = AccountRef(a, AccountKind.RESERVE, ccy, clearing_house)
        reserve_b = AccountRef(b, AccountKind.RESERVE, ccy, clearing_house)
        clearing_a = AccountRef(clearing_house, AccountKind.CLEARING, ccy, a)
        clearing_b = AccountRef(clearing_house, AccountKind.CLEARING, ccy, b)
        steps = (
            Step(
                "SENDING_BANK", a, rail.delays[0], "Sending bank releases the payment order",
                (
                    make_journal(
                        "Send via clearing house",
                        [
                            (in_flight, Side.DEBIT, total),
                            (fee_income, Side.CREDIT, fee_minor),
                            (reserve_a, Side.CREDIT, amount.amount_minor),
                        ],
                    ),
                ),
                "PAYMENT_ORDER",
            ),
            Step(
                "CLEARING", clearing_house, rail.delays[1], "Clearing house settles between banks",
                (
                    make_journal(
                        "Interbank settlement",
                        [
                            (clearing_a, Side.DEBIT, amount.amount_minor),
                            (clearing_b, Side.CREDIT, amount.amount_minor),
                        ],
                    ),
                ),
                "SETTLEMENT_ADVICE",
            ),
            Step(
                "RECEIVING_BANK", b, rail.delays[2], "Receiving bank credits the beneficiary",
                (
                    make_journal(
                        "Credit beneficiary",
                        [
                            (reserve_b, Side.DEBIT, amount.amount_minor),
                            (destination, Side.CREDIT, amount.amount_minor),
                        ],
                    ),
                ),
                "CREDIT_ADVICE",
            ),
        )  # fmt: skip
    fee = Money(fee_minor, ccy)
    figures = {
        "amount": amount.to_dict(),
        "fee": fee.to_dict(),
        "you_pay": Money(total, ccy).to_dict(),
        "beneficiary_receives": amount.to_dict(),
        "rail_label": rail.label,
        "seconds_to_settle": sum(s.delay_seconds for s in steps),
        "simulated": True,
    }
    return TransferPlan(
        "NATIONAL",
        rail.code,
        source,
        destination,
        Money(total, ccy),
        amount,
        fee,
        hold,
        steps,
        figures,
    )


# --- international ----------------------------------------------------------------------------


def plan_international(
    *,
    source: AccountRef,
    destination: AccountRef,
    correspondent: str,
    result: ProviderResult,
    delays: tuple[int, int, int],
) -> TransferPlan:
    """Plan BDT to a foreign account using the fee engine's result for the chosen bank."""
    _customer_check(source, destination)
    ccy = result.target.currency
    if source.currency != BDT:
        raise RailRejected("NOT_BDT_SOURCE", "International transfers start from a BDT account.")
    if destination.currency != ccy:
        raise RailRejected(
            "CURRENCY_MISMATCH", f"The beneficiary account holds {destination.currency}, not {ccy}."
        )
    a, x = source.bank, destination.bank
    target = result.target.amount_minor
    inter, recv = result.intermediary_foreign_minor, result.receiving_foreign_minor
    fixed_foreign = max(result.shortfall_foreign_minor - inter - recv, 0)
    if result.charge_code is ChargeCode.OUR:
        paid_out = target + inter + recv
    elif result.charge_code is ChargeCode.SHA:
        paid_out = target
    else:
        paid_out = target - fixed_foreign
    pay_on = paid_out - inter
    credit = pay_on - recv
    if credit <= 0:
        raise RailRejected("CHARGES_EXCEED_AMOUNT", "The charges would use up the whole amount.")
    if credit != result.beneficiary_receives_minor:
        raise ValueError("bank plan and fee engine disagree about what the beneficiary receives")

    parent_pays = result.parent_pays_bdt_minor
    bank_fees_bdt = result.fixed_fee_paid_by_sender_bdt_minor + result.swift_fee_bdt_minor
    fx_proceeds_bdt = parent_pays - bank_fees_bdt
    in_flight = AccountRef(a, AccountKind.IN_FLIGHT, BDT)
    nostro = AccountRef(a, AccountKind.NOSTRO, ccy, correspondent)
    vostro_a = AccountRef(correspondent, AccountKind.VOSTRO, ccy, a)
    nostro_x = AccountRef(correspondent, AccountKind.NOSTRO, ccy, x)
    vostro_x = AccountRef(x, AccountKind.VOSTRO, ccy, correspondent)

    hold = make_journal(
        "Funds reserved for transfer",
        [(source, Side.DEBIT, parent_pays), (in_flight, Side.CREDIT, parent_pays)],
    )
    release = make_journal(
        "Sell foreign currency, take fees, pay out of nostro",
        [
            (in_flight, Side.DEBIT, parent_pays),
            (AccountRef(a, AccountKind.FEE_INCOME, BDT), Side.CREDIT, bank_fees_bdt),
            (AccountRef(a, AccountKind.FX_POSITION, BDT), Side.CREDIT, fx_proceeds_bdt),
            (AccountRef(a, AccountKind.FX_POSITION, ccy), Side.DEBIT, paid_out + fixed_foreign),
            (nostro, Side.CREDIT, paid_out),
            (AccountRef(a, AccountKind.FEE_INCOME, ccy), Side.CREDIT, fixed_foreign),
        ],
    )
    forward = make_journal(
        "Correspondent forwards the payment",
        [
            (vostro_a, Side.DEBIT, paid_out),
            (AccountRef(correspondent, AccountKind.FEE_INCOME, ccy), Side.CREDIT, inter),
            (nostro_x, Side.CREDIT, pay_on),
        ],
    )
    credit_journal = make_journal(
        "Beneficiary bank credits the customer",
        [
            (vostro_x, Side.DEBIT, pay_on),
            (AccountRef(x, AccountKind.FEE_INCOME, ccy), Side.CREDIT, recv),
            (destination, Side.CREDIT, credit),
        ],
    )
    steps = (
        Step("ORIGINATING_BANK", a, delays[0], "Originating bank sells currency and sends MT103",
             (release,), "MT103"),
        Step("CORRESPONDENT", correspondent, delays[1], "Correspondent forwards through its nostro",
             (forward,), "MT103"),
        Step("BENEFICIARY_BANK", x, delays[2], "Beneficiary bank credits the customer",
             (credit_journal,), "CREDIT_ADVICE"),
    )  # fmt: skip
    fee_total = Money(bank_fees_bdt, BDT)
    figures: dict[str, Any] = {
        "target": result.target.to_dict(),
        "instructed": Money(
            target - (fixed_foreign if result.charge_code is ChargeCode.BEN else 0), ccy
        ).to_dict(),
        "you_pay": Money(parent_pays, BDT).to_dict(),
        "beneficiary_receives": Money(credit, ccy).to_dict(),
        "charge_code": result.charge_code.value,
        "requested_charge_code": result.requested_charge_code.value,
        "provider_id": result.provider_id,
        "provider_rate": str(result.provider_rate),
        "mid_rate": str(result.mid_rate),
        "bank_fees": fee_total.to_dict(),
        "intermediary_fee": Money(inter, ccy).to_dict(),
        "receiving_fee": Money(recv, ccy).to_dict(),
        "fixed_fee_taken_from_amount": Money(fixed_foreign, ccy).to_dict(),
        "total_cost": Money(result.total_cost_bdt_minor, BDT).to_dict(),
        "cost_pct": result.cost_pct_display,
        "seconds_to_settle": sum(delays),
        "simulated": True,
    }
    return TransferPlan(
        "INTERNATIONAL", SWIFT, source, destination, Money(parent_pays, BDT),
        Money(credit, ccy), fee_total, hold, steps, figures,
    )  # fmt: skip


def scale_delays(delays: tuple[int, ...], factor: int) -> tuple[int, ...]:
    return tuple(d * factor for d in delays)
