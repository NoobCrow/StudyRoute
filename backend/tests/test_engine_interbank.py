"""Interbank engine: balanced journals, rails, and numbers that agree with the fee engine."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest

from app.engine.interbank import (
    ON_US,
    AccountKind,
    AccountRef,
    Journal,
    RailRejected,
    RailTerms,
    Side,
    TransferPlan,
    eligible_rails,
    make_journal,
    on_us_terms,
    plan_international,
    plan_national,
    scale_delays,
)
from app.engine.money import Money
from app.engine.quote import ChargeCode, EngineParams, ProviderTerms, compute_provider_result

CCY = "GBP"
CORR = "EXMPUS6C"

# The three providers of config/rules.yaml (all numbers invented).
PROVIDERS = {
    "prov_a": ProviderTerms(
        "prov_a", "Provider A", Decimal("2.00"), 150000, 100000, Decimal(0), Decimal(0),
        (ChargeCode.OUR, ChargeCode.SHA, ChargeCode.BEN), ChargeCode.OUR, 1,
    ),
    "prov_b": ProviderTerms(
        "prov_b", "Provider B", Decimal("1.00"), 300000, 150000, Decimal(30), Decimal(0),
        (ChargeCode.OUR, ChargeCode.SHA, ChargeCode.BEN), ChargeCode.OUR, 2,
    ),
    "prov_c": ProviderTerms(
        "prov_c", "Provider C", Decimal("1.25"), 50000, 0, Decimal(25), Decimal(10),
        (ChargeCode.SHA,), ChargeCode.SHA, 3,
    ),
}  # fmt: skip

BDT_INSTANT = RailTerms("INSTANT", "Instant", "BDT", 500, 0, 100, 50_000_000, (1, 1, 1))
BDT_BATCH = RailTerms("BATCH", "Batch", "BDT", 200, 0, 100, 500_000_000, (20, 3, 3))
BDT_HIGH = RailTerms("HIGH_VALUE", "High value", "BDT", 10_000, 0, 50_000_000, None, (3, 3, 3))


def customer(bank: str, number: str, currency: str = "BDT") -> AccountRef:
    return AccountRef(bank, AccountKind.CUSTOMER, currency, number=number)


class Books:
    """A tiny ledger: applies journals the way the domain does and tracks signed balances."""

    def __init__(self) -> None:
        self.balance: dict[AccountRef, int] = defaultdict(int)

    def apply(self, journal: Journal) -> None:
        from app.engine.interbank import NORMAL_SIDE

        for p in journal.postings:
            sign = 1 if p.side is NORMAL_SIDE[p.account.kind] else -1
            self.balance[p.account] += sign * p.amount_minor


def run(plan: TransferPlan) -> Books:
    books = Books()
    for journal in plan.all_journals():
        books.apply(journal)
    return books


def international(provider: str, code: ChargeCode, target_major: int = 10_000) -> TransferPlan:
    result = compute_provider_result(
        target=Money(target_major * 100, CCY),
        mid_rate=Decimal("160.000000"),
        terms=PROVIDERS[provider],
        requested_charge_code=code,
        params=EngineParams(),
    )
    bank = {"prov_a": "EXMPBDA1", "prov_b": "EXMPBDB1", "prov_c": "EXMPBDC1"}[provider]
    return plan_international(
        source=customer(bank, "SBX-A-0001"),
        destination=customer("EXMPGB2L", "GB08EXMP12345612344821", CCY),
        correspondent=CORR,
        result=result,
        delays=(4, 4, 4),
    )


# --- journals ----------------------------------------------------------------------------------


def test_an_unbalanced_journal_is_refused() -> None:
    a, b = customer("EXMPBDA1", "x"), customer("EXMPBDA1", "y")
    with pytest.raises(ValueError, match="unbalanced"):
        make_journal("bad", [(a, Side.DEBIT, 100), (b, Side.CREDIT, 99)])


def test_zero_lines_are_dropped_and_the_rest_balance() -> None:
    a, b = customer("EXMPBDA1", "x"), customer("EXMPBDA1", "y")
    fee = AccountRef("EXMPBDA1", AccountKind.FEE_INCOME, "BDT")
    journal = make_journal(
        "ok", [(a, Side.DEBIT, 100), (b, Side.CREDIT, 100), (fee, Side.CREDIT, 0)]
    )
    assert len(journal.postings) == 2 and journal.is_balanced()


def test_a_reversed_journal_cancels_the_original() -> None:
    plan = plan_national(
        source=customer("EXMPBDA1", "a"), destination=customer("EXMPBDB1", "b"),
        amount=Money(100_000, "BDT"), rail=BDT_INSTANT, clearing_house="CLR-BD",
    )  # fmt: skip
    books = Books()
    for journal in plan.all_journals():
        books.apply(journal)
    for journal in reversed(plan.all_journals()):
        books.apply(journal.reversed())
    assert all(v == 0 for v in books.balance.values())


def test_a_posting_must_be_a_positive_integer() -> None:
    from app.engine.interbank import Posting

    ref = customer("EXMPBDA1", "x")
    with pytest.raises(ValueError):
        Posting(ref, Side.DEBIT, 0)
    with pytest.raises(TypeError):
        Posting(ref, Side.DEBIT, 1.5)  # type: ignore[arg-type]


# --- national ----------------------------------------------------------------------------------


def test_a_same_bank_transfer_is_free_and_one_step() -> None:
    plan = plan_national(
        source=customer("EXMPBDA1", "a"), destination=customer("EXMPBDA1", "b"),
        amount=Money(250_000, "BDT"), rail=on_us_terms("BDT", (1,)), clearing_house=None,
    )  # fmt: skip
    assert plan.rail == ON_US and plan.fee.amount_minor == 0
    assert plan.debit == plan.credit == Money(250_000, "BDT")
    assert [s.stage for s in plan.steps] == ["CREDIT_BENEFICIARY"]
    books = run(plan)
    assert books.balance[customer("EXMPBDA1", "a")] == -250_000
    assert books.balance[customer("EXMPBDA1", "b")] == 250_000


def test_an_interbank_transfer_charges_the_sender_and_credits_the_receiver() -> None:
    src, dst = customer("EXMPBDA1", "a"), customer("EXMPBDB1", "b")
    plan = plan_national(
        source=src, destination=dst, amount=Money(100_000, "BDT"), rail=BDT_INSTANT,
        clearing_house="CLR-BD",
    )  # fmt: skip
    assert plan.fee.amount_minor == 500
    assert plan.debit == Money(100_500, "BDT") and plan.credit == Money(100_000, "BDT")
    assert [s.stage for s in plan.steps] == ["SENDING_BANK", "CLEARING", "RECEIVING_BANK"]
    books = run(plan)
    assert books.balance[src] == -100_500 and books.balance[dst] == 100_000
    assert books.balance[AccountRef("EXMPBDA1", AccountKind.FEE_INCOME, "BDT")] == 500
    assert books.balance[AccountRef("EXMPBDA1", AccountKind.IN_FLIGHT, "BDT")] == 0


def test_the_clearing_house_mirrors_each_banks_reserve() -> None:
    plan = plan_national(
        source=customer("EXMPBDA1", "a"), destination=customer("EXMPBDB1", "b"),
        amount=Money(100_000, "BDT"), rail=BDT_BATCH, clearing_house="CLR-BD",
    )  # fmt: skip
    books = run(plan)
    for bank in ("EXMPBDA1", "EXMPBDB1"):
        reserve = AccountRef(bank, AccountKind.RESERVE, "BDT", "CLR-BD")
        mirror = reserve.mirror()
        assert mirror is not None
        assert books.balance[reserve] == books.balance[mirror]


@pytest.mark.parametrize(
    ("rail", "amount", "code"),
    [
        (BDT_INSTANT, 99, "BELOW_RAIL_MINIMUM"),
        (BDT_INSTANT, 50_000_001, "ABOVE_RAIL_MAXIMUM"),
        (BDT_HIGH, 49_999_999, "BELOW_RAIL_MINIMUM"),
        (BDT_BATCH, 500_000_001, "ABOVE_RAIL_MAXIMUM"),
    ],
)
def test_rail_limits_are_enforced(rail: RailTerms, amount: int, code: str) -> None:
    with pytest.raises(RailRejected) as caught:
        plan_national(
            source=customer("EXMPBDA1", "a"), destination=customer("EXMPBDB1", "b"),
            amount=Money(amount, "BDT"), rail=rail, clearing_house="CLR-BD",
        )  # fmt: skip
    assert caught.value.code == code


def test_a_national_transfer_cannot_change_currency() -> None:
    with pytest.raises(RailRejected) as caught:
        plan_national(
            source=customer("EXMPBDA1", "a"), destination=customer("EXMPGB2L", "g", "GBP"),
            amount=Money(100_000, "BDT"), rail=BDT_INSTANT, clearing_house="CLR-BD",
        )  # fmt: skip
    assert caught.value.code == "CURRENCY_MISMATCH"


def test_sending_to_the_same_account_is_refused() -> None:
    same = customer("EXMPBDA1", "a")
    with pytest.raises(RailRejected) as caught:
        plan_national(
            source=same, destination=same, amount=Money(100_000, "BDT"),
            rail=on_us_terms("BDT", (1,)), clearing_house=None,
        )  # fmt: skip
    assert caught.value.code == "SAME_ACCOUNT"


def test_eligible_rails_are_listed_cheapest_first() -> None:
    rails = {"INSTANT": BDT_INSTANT, "BATCH": BDT_BATCH, "HIGH_VALUE": BDT_HIGH}
    small = [r.code for r in eligible_rails(rails, Money(100_000, "BDT"))]
    assert small == ["BATCH", "INSTANT"]
    large = [r.code for r in eligible_rails(rails, Money(60_000_000, "BDT"))]
    assert large == ["BATCH", "HIGH_VALUE"]
    assert eligible_rails(rails, Money(50, "BDT")) == []


def test_scaled_delays_multiply_every_step() -> None:
    assert scale_delays((4, 4, 4), 6) == (24, 24, 24)


# --- international -----------------------------------------------------------------------------


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
@pytest.mark.parametrize("code", list(ChargeCode))
def test_the_bank_plan_agrees_with_the_fee_engine(provider: str, code: ChargeCode) -> None:
    result = compute_provider_result(
        target=Money(1_000_000, CCY), mid_rate=Decimal("160.000000"), terms=PROVIDERS[provider],
        requested_charge_code=code, params=EngineParams(),
    )  # fmt: skip
    plan = international(provider, code)
    assert plan.debit.amount_minor == result.parent_pays_bdt_minor
    assert plan.credit.amount_minor == result.beneficiary_receives_minor
    assert plan.figures["charge_code"] == result.charge_code.value
    assert all(j.is_balanced() for j in plan.all_journals())


@pytest.mark.parametrize("provider", sorted(PROVIDERS))
@pytest.mark.parametrize("code", list(ChargeCode))
def test_international_books_balance_and_mirror_accounts_agree(
    provider: str, code: ChargeCode
) -> None:
    plan = international(provider, code)
    books = run(plan)
    src, dst = plan.source, plan.destination
    assert books.balance[src] == -plan.debit.amount_minor
    assert books.balance[dst] == plan.credit.amount_minor
    originating = src.bank
    assert books.balance[AccountRef(originating, AccountKind.IN_FLIGHT, "BDT")] == 0
    nostro = AccountRef(originating, AccountKind.NOSTRO, CCY, CORR)
    vostro = nostro.mirror()
    assert vostro is not None and books.balance[nostro] == books.balance[vostro]
    nostro_x = AccountRef(CORR, AccountKind.NOSTRO, CCY, dst.bank)
    vostro_x = nostro_x.mirror()
    assert vostro_x is not None and books.balance[nostro_x] == books.balance[vostro_x]
    # Everything the parent paid ends up as customer credit plus the three banks' income and the
    # FX position; nothing is created or lost.
    income = sum(
        v
        for ref, v in books.balance.items()
        if ref.kind is AccountKind.FEE_INCOME and ref.currency == "BDT"
    )
    assert income == plan.fee.amount_minor


def test_our_prepays_the_charges_so_the_beneficiary_gets_the_full_amount() -> None:
    plan = international("prov_c", ChargeCode.OUR)  # prov_c only offers SHA: falls back
    assert plan.figures["charge_code"] == "SHA"
    plan_b = international("prov_b", ChargeCode.OUR)
    assert plan_b.credit == Money(1_000_000, CCY)
    assert plan_b.figures["requested_charge_code"] == "OUR"


def test_sha_and_ben_deduct_charges_from_the_amount() -> None:
    sha = international("prov_b", ChargeCode.SHA)
    ben = international("prov_b", ChargeCode.BEN)
    assert sha.credit.amount_minor == 1_000_000 - 3000
    assert ben.credit.amount_minor < sha.credit.amount_minor
    assert ben.figures["fixed_fee_taken_from_amount"]["amount_minor"] > 0


def test_each_hop_is_a_separate_step_with_its_own_bank() -> None:
    plan = international("prov_a", ChargeCode.OUR)
    assert [(s.stage, s.bank) for s in plan.steps] == [
        ("ORIGINATING_BANK", "EXMPBDA1"),
        ("CORRESPONDENT", CORR),
        ("BENEFICIARY_BANK", "EXMPGB2L"),
    ]
    assert [s.message for s in plan.steps] == ["MT103", "MT103", "CREDIT_ADVICE"]


def test_charges_larger_than_the_amount_are_refused() -> None:
    with pytest.raises(RailRejected) as caught:
        international("prov_c", ChargeCode.SHA, target_major=30)
    assert caught.value.code == "CHARGES_EXCEED_AMOUNT"


def test_international_needs_a_bdt_source_and_a_matching_destination_currency() -> None:
    result = compute_provider_result(
        target=Money(1_000_000, CCY), mid_rate=Decimal("160"), terms=PROVIDERS["prov_a"],
        requested_charge_code=ChargeCode.OUR, params=EngineParams(),
    )  # fmt: skip
    with pytest.raises(RailRejected) as not_bdt:
        plan_international(
            source=customer("EXMPGB2X", "s", "GBP"), destination=customer("EXMPGB2L", "d", CCY),
            correspondent=CORR, result=result, delays=(4, 4, 4),
        )  # fmt: skip
    assert not_bdt.value.code == "NOT_BDT_SOURCE"
    with pytest.raises(RailRejected) as wrong:
        plan_international(
            source=customer("EXMPBDA1", "s"), destination=customer("EXMPUS33", "d", "USD"),
            correspondent=CORR, result=result, delays=(4, 4, 4),
        )  # fmt: skip
    assert wrong.value.code == "CURRENCY_MISMATCH"


# --- serialisation -----------------------------------------------------------------------------


def test_a_plan_survives_a_round_trip_and_keeps_its_hash() -> None:
    plan = international("prov_b", ChargeCode.OUR)
    again = TransferPlan.from_dict(plan.to_dict())
    assert again == plan and again.plan_hash == plan.plan_hash
    changed = international("prov_b", ChargeCode.SHA)
    assert changed.plan_hash != plan.plan_hash


def test_money_in_a_plan_is_integer_minor_units() -> None:
    plan = international("prov_a", ChargeCode.OUR)
    for journal in plan.all_journals():
        for posting in journal.postings:
            assert isinstance(posting.amount_minor, int)
