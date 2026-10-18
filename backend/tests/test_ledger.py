"""The ledger: normal-side balances, overdraft refusal, reversals, integrity checks, append-only."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DatabaseError

from app.core.clock import FakeClock
from app.core.db import Database
from app.domain.ledger import (
    INSUFFICIENT_FUNDS,
    INSUFFICIENT_LIQUIDITY,
    UNKNOWN_ACCOUNT,
    Ledger,
    LedgerError,
)
from app.engine.interbank import AccountKind, AccountRef, Side, make_journal
from app.models import BankAccount, LedgerEntry

BANK = "EXMPBDA1"
OTHER = "EXMPBDB1"
CUSTOMER = AccountRef(BANK, AccountKind.CUSTOMER, "BDT", number="SBX-A-0001")
FRIEND = AccountRef(OTHER, AccountKind.CUSTOMER, "BDT", number="SBX-B-0001")
CASH_A = AccountRef(BANK, AccountKind.CASH, "BDT")
CASH_B = AccountRef(OTHER, AccountKind.CASH, "BDT")
NOSTRO = AccountRef(BANK, AccountKind.NOSTRO, "GBP", "EXMPUS6C")
VOSTRO = NOSTRO.mirror()


@pytest.fixture
def ledger(clock: FakeClock) -> Ledger:
    return Ledger(clock)


@pytest.fixture
def funded(db: Database, ledger: Ledger) -> Database:
    """A customer holding BDT 1,000.00 (opening journal against the bank's cash)."""
    with db.write() as session:
        for ref in (CUSTOMER, FRIEND, CASH_A, CASH_B):
            ledger.open_account(session, ref, holder="x")
        opening = make_journal(
            "Opening", [(CASH_A, Side.DEBIT, 100_000), (CUSTOMER, Side.CREDIT, 100_000)]
        )
        ledger.post(session, opening, transfer_id=None, kind="OPENING")
    return db


def balance(db: Database, ledger: Ledger, ref: AccountRef) -> int:
    with db.read() as session:
        return ledger.require(session, ref).balance_minor


def test_opening_an_account_twice_returns_the_same_row(db: Database, ledger: Ledger) -> None:
    with db.write() as session:
        first, created_first = ledger.open_account(session, CUSTOMER, holder="A")
        second, created_second = ledger.open_account(session, CUSTOMER, holder="A")
    assert first.id == second.id and created_first and not created_second


def test_postings_move_balances_on_each_accounts_normal_side(
    funded: Database, ledger: Ledger
) -> None:
    # A customer deposit is credit-normal: the opening credit raised it, a debit lowers it.
    assert balance(funded, ledger, CUSTOMER) == 100_000
    assert balance(funded, ledger, CASH_A) == 100_000  # cash is debit-normal
    with funded.write() as session:
        pay = make_journal("Pay", [(CUSTOMER, Side.DEBIT, 30_000), (FRIEND, Side.CREDIT, 30_000)])
        ledger.post(session, pay, transfer_id=None, kind="STEP")
    assert balance(funded, ledger, CUSTOMER) == 70_000
    assert balance(funded, ledger, FRIEND) == 30_000


def test_an_overdraft_is_refused_and_nothing_changes(funded: Database, ledger: Ledger) -> None:
    too_much = make_journal(
        "Too much", [(CUSTOMER, Side.DEBIT, 100_001), (FRIEND, Side.CREDIT, 100_001)]
    )
    with funded.write() as session, pytest.raises(LedgerError) as caught:
        ledger.post(session, too_much, transfer_id=None, kind="STEP")
    assert caught.value.code == INSUFFICIENT_FUNDS
    assert balance(funded, ledger, CUSTOMER) == 100_000
    assert balance(funded, ledger, FRIEND) == 0
    with funded.read() as session:
        assert session.query(LedgerEntry).count() == 2  # only the opening journal


def test_a_bank_account_that_would_run_dry_reports_liquidity(db: Database, ledger: Ledger) -> None:
    fx = AccountRef(BANK, AccountKind.FX_POSITION, "GBP")
    with db.write() as session:
        for ref in (NOSTRO, VOSTRO, fx):
            assert ref is not None
            ledger.open_account(session, ref)
        pay = make_journal(
            "Pay out of an empty nostro", [(fx, Side.DEBIT, 5), (NOSTRO, Side.CREDIT, 5)]
        )
        with pytest.raises(LedgerError) as caught:
            ledger.post(session, pay, transfer_id=None, kind="STEP")
    assert caught.value.code == INSUFFICIENT_LIQUIDITY


def test_cash_and_fx_positions_may_go_short(db: Database, ledger: Ledger) -> None:
    fx = AccountRef(BANK, AccountKind.FX_POSITION, "BDT")
    with db.write() as session:
        ledger.open_account(session, fx)
        ledger.open_account(session, CASH_A)
        journal = make_journal("Short position", [(fx, Side.CREDIT, 50), (CASH_A, Side.DEBIT, 50)])
        ledger.post(session, journal, transfer_id=None, kind="STEP")
    assert balance(db, ledger, fx) == -50


def test_an_unknown_account_is_reported(db: Database, ledger: Ledger) -> None:
    journal = make_journal("Ghost", [(CUSTOMER, Side.DEBIT, 1), (FRIEND, Side.CREDIT, 1)])
    with db.write() as session, pytest.raises(LedgerError) as caught:
        ledger.post(session, journal, transfer_id=None, kind="STEP")
    assert caught.value.code == UNKNOWN_ACCOUNT


def test_a_reversal_restores_every_balance(funded: Database, ledger: Ledger) -> None:
    pay = make_journal("Pay", [(CUSTOMER, Side.DEBIT, 40_000), (FRIEND, Side.CREDIT, 40_000)])
    with funded.write() as session:
        ledger.post(session, pay, transfer_id=None, kind="STEP")
        ledger.post(session, pay.reversed(), transfer_id=None, kind="REVERSAL")
    assert balance(funded, ledger, CUSTOMER) == 100_000
    assert balance(funded, ledger, FRIEND) == 0


def test_the_trial_balance_balances_in_every_currency(funded: Database, ledger: Ledger) -> None:
    with funded.read() as session:
        totals = ledger.trial_balance(session)
    assert totals["BDT"] == {"debits": 100_000, "credits": 100_000, "balanced": True}


def test_mirror_accounts_reconcile_until_one_side_is_edited(db: Database, ledger: Ledger) -> None:
    assert VOSTRO is not None
    fx = AccountRef(BANK, AccountKind.FX_POSITION, "GBP")
    cash_corr = AccountRef("EXMPUS6C", AccountKind.CASH, "GBP")
    cash_a = AccountRef(BANK, AccountKind.CASH, "GBP")
    with db.write() as session:
        for ref in (NOSTRO, VOSTRO, fx, cash_corr, cash_a):
            ledger.open_account(session, ref)
        ledger.post(
            session,
            make_journal(
                "A funds its nostro", [(NOSTRO, Side.DEBIT, 1000), (cash_a, Side.CREDIT, 1000)]
            ),
            transfer_id=None,
            kind="OPENING",
        )
        ledger.post(
            session,
            make_journal(
                "Correspondent books it",
                [(cash_corr, Side.DEBIT, 1000), (VOSTRO, Side.CREDIT, 1000)],
            ),
            transfer_id=None,
            kind="OPENING",
        )
    with db.read() as session:
        report = ledger.mirror_report(session)
    assert [r["reconciled"] for r in report] == [True]
    with db.write() as session:
        session.execute(
            update(BankAccount).where(BankAccount.kind == "VOSTRO").values(balance_minor=999)
        )
    with db.read() as session:
        assert [r["reconciled"] for r in ledger.mirror_report(session)] == [False]
        assert len(ledger.balances_that_do_not_match_entries(session)) == 1


def test_stored_balances_agree_with_entries_when_nobody_tampered(
    funded: Database, ledger: Ledger
) -> None:
    with funded.read() as session:
        assert ledger.balances_that_do_not_match_entries(session) == []


def test_entries_and_journals_are_append_only(funded: Database) -> None:
    with funded.write() as session, pytest.raises(DatabaseError, match="append-only"):
        session.execute(update(LedgerEntry).values(amount_minor=1))
    with funded.write() as session, pytest.raises(DatabaseError, match="append-only"):
        session.execute(delete(LedgerEntry))
    with funded.write() as session, pytest.raises(DatabaseError, match="append-only"):
        session.execute(text("DELETE FROM ledger_journals"))


def test_the_statement_lists_newest_first_with_running_balances(
    funded: Database, ledger: Ledger
) -> None:
    pay = make_journal("Pay", [(CUSTOMER, Side.DEBIT, 10_000), (FRIEND, Side.CREDIT, 10_000)])
    with funded.write() as session:
        ledger.post(session, pay, transfer_id=None, kind="STEP")
    with funded.read() as session:
        account = ledger.require(session, CUSTOMER)
        lines = ledger.statement(session, account.id)
    assert [
        (line["side"], line["amount_minor"], line["balance_after_minor"]) for line in lines
    ] == [
        ("DEBIT", 10_000, 90_000),
        ("CREDIT", 100_000, 100_000),
    ]
