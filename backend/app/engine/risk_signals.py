"""Signals that a payment should be looked at by a person at the bank. Pure: no database, no clock.

A signal is a reason to look, with the figures behind it. It is never a conclusion: nothing here
says a payment is illegal, and a payment with no signals is not thereby "legal". The thresholds
come from config/rules.yaml (marked unverified) and the answer is always "Indicative. Confirm
with your AD bank." Money is integer minor units.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LARGE_AMOUNT = "LARGE_AMOUNT"
POSSIBLE_SPLIT = "POSSIBLE_SPLIT"
NAME_CHECK = "NAME_CHECK"
NEW_RECIPIENT = "NEW_RECIPIENT"
NO_INVOICE = "NO_INVOICE"


@dataclass(frozen=True)
class ReviewFacts:
    amount_usd_minor: int
    earlier_usd_minor: tuple[
        int, ...
    ]  # this household's other payments inside the look-back window
    recipient_first_payment: bool
    recipient_name_flagged: bool  # matches the sandbox's name-check test token
    has_invoice_on_file: bool
    purpose: str


@dataclass(frozen=True)
class ReviewParams:
    large_usd_minor: int
    split_min_payments: int
    split_window_days: int


@dataclass(frozen=True)
class Signal:
    code: str
    needs_human: bool  # True: a reviewer must decide. False: shown as context only.
    figures: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "needs_human": self.needs_human, "figures": dict(self.figures)}


def usd(minor: int) -> str:
    return f"USD {minor // 100:,}.{minor % 100:02d}"


def find_signals(facts: ReviewFacts, params: ReviewParams) -> list[Signal]:
    signals: list[Signal] = []
    if facts.amount_usd_minor >= params.large_usd_minor:
        signals.append(
            Signal(
                LARGE_AMOUNT,
                True,
                {"amount": usd(facts.amount_usd_minor), "line": usd(params.large_usd_minor)},
            )
        )
    count = len(facts.earlier_usd_minor) + 1
    total = sum(facts.earlier_usd_minor) + facts.amount_usd_minor
    if (
        facts.amount_usd_minor < params.large_usd_minor
        and count >= params.split_min_payments
        and total >= params.large_usd_minor
    ):
        signals.append(
            Signal(
                POSSIBLE_SPLIT,
                True,
                {
                    "payments": str(count),
                    "days": str(params.split_window_days),
                    "total": usd(total),
                    "line": usd(params.large_usd_minor),
                },
            )
        )
    if facts.recipient_name_flagged:
        signals.append(Signal(NAME_CHECK, True))
    if facts.recipient_first_payment:
        signals.append(Signal(NEW_RECIPIENT, False))
    if facts.purpose == "TUITION" and not facts.has_invoice_on_file:
        signals.append(Signal(NO_INVOICE, False))
    return signals


def needs_human(signals: list[Signal]) -> bool:
    return any(signal.needs_human for signal in signals)
