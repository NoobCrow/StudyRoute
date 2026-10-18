"""The sandbox ledger: double-entry accounts, balanced journals, reversals and integrity checks.

Journals come from the pure interbank engine. This module only resolves account names to rows,
applies each posting on the account's normal side, refuses a journal that would overdraw an
account, and writes append-only journal and entry rows. Nothing here talks to a real bank.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock, iso_utc
from app.core.ids import new_id
from app.engine.interbank import (
    ALLOWS_NEGATIVE,
    NORMAL_SIDE,
    AccountKind,
    AccountRef,
    Journal,
    Side,
)
from app.models import BankAccount, LedgerEntry, LedgerJournal

INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
INSUFFICIENT_LIQUIDITY = "INSUFFICIENT_LIQUIDITY"
UNKNOWN_ACCOUNT = "UNKNOWN_ACCOUNT"


class LedgerError(Exception):
    """A journal could not be posted. `code` is a stable machine reason."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def ref_of(account: BankAccount) -> AccountRef:
    return AccountRef(
        account.bank_code,
        AccountKind(account.kind),
        account.currency,
        account.counterparty,
        account.number,
    )


def _signed(account_kind: str, side: str, amount: int) -> int:
    """+amount when the posting is on the account's normal side, -amount otherwise."""
    return amount if NORMAL_SIDE[AccountKind(account_kind)].value == side else -amount


class Ledger:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock

    # --- accounts -------------------------------------------------------------------------
    def find(self, session: Session, ref: AccountRef) -> BankAccount | None:
        return session.execute(
            select(BankAccount).where(
                BankAccount.bank_code == ref.bank,
                BankAccount.kind == ref.kind.value,
                BankAccount.currency == ref.currency,
                BankAccount.counterparty == ref.counterparty,
                BankAccount.number == ref.number,
            )
        ).scalar_one_or_none()

    def require(self, session: Session, ref: AccountRef) -> BankAccount:
        account = self.find(session, ref)
        if account is None:
            raise LedgerError(UNKNOWN_ACCOUNT, f"No ledger account for {ref.to_dict()}.")
        return account

    def open_account(
        self,
        session: Session,
        ref: AccountRef,
        *,
        holder: str = "",
        label: str = "",
        owner_id: str | None = None,
    ) -> tuple[BankAccount, bool]:
        """Get the account, creating it with a zero balance when it does not exist yet."""
        existing = self.find(session, ref)
        if existing is not None:
            return existing, False
        account = BankAccount(
            id=new_id("bacc"),
            bank_code=ref.bank,
            kind=ref.kind.value,
            currency=ref.currency,
            counterparty=ref.counterparty,
            number=ref.number,
            holder_name=holder,
            label=label,
            owner_id=owner_id,
            balance_minor=0,
            allow_negative=ref.kind in ALLOWS_NEGATIVE,
            created_at=self._clock.now(),
        )
        session.add(account)
        session.flush()
        return account, True

    # --- posting --------------------------------------------------------------------------
    def post(
        self,
        session: Session,
        journal: Journal,
        *,
        transfer_id: str | None,
        kind: str,
        stage: str = "",
        seq: int = 0,
    ) -> LedgerJournal:
        """Apply a balanced journal, or raise LedgerError before changing anything."""
        if not journal.is_balanced():
            raise LedgerError("UNBALANCED", f"Journal is not balanced: {journal.memo}")
        accounts: dict[AccountRef, BankAccount] = {}
        net: dict[str, int] = {}
        for posting in journal.postings:
            account = accounts.get(posting.account) or self.require(session, posting.account)
            accounts[posting.account] = account
            net[account.id] = net.get(account.id, 0) + _signed(
                account.kind, posting.side.value, posting.amount_minor
            )
        for account in accounts.values():
            if not account.allow_negative and account.balance_minor + net[account.id] < 0:
                code = (
                    INSUFFICIENT_FUNDS
                    if account.kind == AccountKind.CUSTOMER.value
                    else INSUFFICIENT_LIQUIDITY
                )
                raise LedgerError(code, f"Not enough funds in the {account.kind} account.")
        row = LedgerJournal(
            id=new_id("jrn"),
            transfer_id=transfer_id,
            seq=seq,
            kind=kind,
            stage=stage,
            memo=journal.memo[:160],
            posted_at=self._clock.now(),
        )
        session.add(row)
        session.flush()
        for posting in journal.postings:
            account = accounts[posting.account]
            account.balance_minor += _signed(account.kind, posting.side.value, posting.amount_minor)
            session.add(
                LedgerEntry(
                    journal_id=row.id,
                    account_id=account.id,
                    side=posting.side.value,
                    amount_minor=posting.amount_minor,
                    currency=account.currency,
                    balance_after_minor=account.balance_minor,
                )
            )
        session.flush()
        return row

    # --- reports and integrity checks -------------------------------------------------------
    def trial_balance(self, session: Session) -> dict[str, dict[str, Any]]:
        """Total debits and credits ever posted, per currency. They must be equal."""
        rows = session.execute(
            select(LedgerEntry.currency, LedgerEntry.side, func.sum(LedgerEntry.amount_minor))
            .group_by(LedgerEntry.currency, LedgerEntry.side)
            .order_by(LedgerEntry.currency)
        ).all()
        totals: dict[str, dict[str, Any]] = {}
        for currency, side, total in rows:
            entry = totals.setdefault(currency, {"debits": 0, "credits": 0})
            entry["debits" if side == Side.DEBIT.value else "credits"] = int(total)
        for entry in totals.values():
            entry["balanced"] = entry["debits"] == entry["credits"]
        return totals

    def mirror_report(self, session: Session) -> list[dict[str, Any]]:
        """Each nostro/reserve against the liability the other institution keeps for it."""
        accounts = session.execute(select(BankAccount)).scalars().all()
        by_ref = {ref_of(a): a for a in accounts}
        report = []
        for account in accounts:
            if account.kind not in (AccountKind.NOSTRO.value, AccountKind.RESERVE.value):
                continue
            mirror = by_ref.get(ref_of(account).mirror()) if ref_of(account).mirror() else None
            report.append(
                {
                    "kind": account.kind,
                    "holder_bank": account.bank_code,
                    "other_institution": account.counterparty,
                    "currency": account.currency,
                    "holder_balance_minor": account.balance_minor,
                    "other_balance_minor": mirror.balance_minor if mirror else None,
                    "reconciled": mirror is not None
                    and mirror.balance_minor == account.balance_minor,
                }
            )
        return sorted(
            report, key=lambda r: (r["holder_bank"], r["other_institution"], r["currency"])
        )

    def balances_that_do_not_match_entries(self, session: Session) -> list[str]:
        """Accounts whose stored balance differs from the sum of their entries (tampering check)."""
        sums: dict[str, int] = {}
        rows = session.execute(
            select(
                LedgerEntry.account_id,
                LedgerEntry.side,
                func.sum(LedgerEntry.amount_minor),
            ).group_by(LedgerEntry.account_id, LedgerEntry.side)
        ).all()
        kinds = {a.id: a for a in session.execute(select(BankAccount)).scalars().all()}
        for account_id, side, total in rows:
            sums[account_id] = sums.get(account_id, 0) + _signed(
                kinds[account_id].kind, side, int(total)
            )
        return sorted(a.id for a in kinds.values() if a.balance_minor != sums.get(a.id, 0))

    def statement(self, session: Session, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = session.execute(
            select(LedgerEntry, LedgerJournal)
            .join(LedgerJournal, LedgerJournal.id == LedgerEntry.journal_id)
            .where(LedgerEntry.account_id == account_id)
            .order_by(LedgerEntry.id.desc())
            .limit(limit)
        ).all()
        return [
            {
                "at": iso_utc(journal.posted_at),
                "memo": journal.memo,
                "stage": journal.stage,
                "transfer_id": journal.transfer_id,
                "side": entry.side,
                "amount_minor": entry.amount_minor,
                "currency": entry.currency,
                "balance_after_minor": entry.balance_after_minor,
            }
            for entry, journal in rows
        ]
