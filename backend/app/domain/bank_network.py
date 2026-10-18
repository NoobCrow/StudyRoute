"""The sandbox bank network: fake banks that move simulated money between synthetic accounts.

A human with a fresh MFA proof confirms a transfer; from then on the simulator advances it one
hop at a time (originating bank, correspondent, beneficiary bank, or sender, clearing house,
receiver). Each hop posts a balanced journal to the ledger and writes ONE audit event in the same
transaction. A transfer that fails is unwound exactly, so the payer gets everything back.

Nothing here contacts a real bank. Every bank, account, rate, fee and limit is invented.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.ids import new_id
from app.domain import auth
from app.domain.bank_directory import AD_BANK, HOST_BANK, BankDirectory
from app.domain.compliance import is_sanctions_hit, scenario_for
from app.domain.constants import BankTransferStatus, Decision
from app.domain.ledger import Ledger, LedgerError, ref_of
from app.domain.limits import evaluate_limits, usd_equivalent_minor
from app.domain.rbac import SYSTEM_ACTOR, Actor, Perm, authorize
from app.domain.rules import Rules
from app.engine import fx
from app.engine.interbank import (
    ON_US,
    AccountKind,
    AccountRef,
    RailRejected,
    Side,
    TransferPlan,
    eligible_rails,
    make_journal,
    on_us_terms,
    plan_international,
    plan_national,
    scale_delays,
)
from app.engine.money import EngineError, Money, round_half_up
from app.engine.mt103 import build_instruction_preview
from app.engine.quote import ChargeCode, compute_provider_result
from app.engine.validators import mask_account
from app.models import (
    BankAccount,
    BankTransfer,
    BankTransferEvent,
    LedgerEntry,
    LedgerJournal,
    MfaProof,
    User,
)
from app.providers.base import Scenario

MFA_SCOPE = "confirm_bank_transfer"
NATIONAL = "NATIONAL"
INTERNATIONAL = "INTERNATIONAL"
OPEN_STATES = (BankTransferStatus.ACCEPTED.value, BankTransferStatus.IN_TRANSIT.value)

FAILURE_TEXT = {
    "BENEFICIARY_REJECTED": "The beneficiary bank rejected the payment (simulated).",
    "INSUFFICIENT_LIQUIDITY": "A bank in the chain had too little liquidity (simulated).",
    "INSUFFICIENT_FUNDS": "An account did not hold enough funds (simulated).",
    "SANDBOX_FORCED": "A reviewer made this transfer fail to show the return flow (simulated).",
}


class BankNetworkService:
    def __init__(
        self, clock: Clock, audit: AuditService, ledger: Ledger, directory: BankDirectory
    ) -> None:
        self._clock = clock
        self._audit = audit
        self.ledger = ledger
        self.directory = directory

    # --- setting up the network -----------------------------------------------------------------
    def _infrastructure(self) -> tuple[list[AccountRef], list[tuple[AccountRef, AccountRef, int]]]:
        """Every bank-internal account, and the (asset, liability, amount) pairs to fund."""
        d = self.directory
        corr = d.correspondent
        refs: list[AccountRef] = []
        funding: list[tuple[AccountRef, AccountRef, int]] = []

        def add(*new: AccountRef) -> None:
            refs.extend(r for r in new if r not in refs)

        for bank in d.banks.values():
            if bank.code == corr.code:
                continue
            add(
                AccountRef(bank.code, AccountKind.IN_FLIGHT, bank.currency),
                AccountRef(bank.code, AccountKind.FEE_INCOME, bank.currency),
                AccountRef(bank.code, AccountKind.CASH, bank.currency),
            )
        for ccy in d.host_currencies():
            add(
                AccountRef(corr.code, AccountKind.FEE_INCOME, ccy),
                AccountRef(corr.code, AccountKind.CASH, ccy),
            )
        for ad in d.with_role(AD_BANK):
            add(AccountRef(ad.code, AccountKind.FX_POSITION, ad.currency))
            for ccy in d.host_currencies():
                nostro = AccountRef(ad.code, AccountKind.NOSTRO, ccy, corr.code)
                vostro = AccountRef(corr.code, AccountKind.VOSTRO, ccy, ad.code)
                add(
                    nostro,
                    vostro,
                    AccountRef(ad.code, AccountKind.FX_POSITION, ccy),
                    AccountRef(ad.code, AccountKind.FEE_INCOME, ccy),
                    AccountRef(ad.code, AccountKind.CASH, ccy),
                )
                funding.append((nostro, vostro, d.opening_minor(ccy, d.nostro_major)))
        for host in d.with_role(HOST_BANK):
            nostro = AccountRef(corr.code, AccountKind.NOSTRO, host.currency, host.code)
            vostro = AccountRef(host.code, AccountKind.VOSTRO, host.currency, corr.code)
            add(nostro, vostro)
            funding.append((nostro, vostro, d.opening_minor(host.currency, d.nostro_major)))
        for bank in d.banks.values():
            house = d.clearing_house_for(bank)
            if house is None or bank.code == corr.code:
                continue
            reserve = AccountRef(bank.code, AccountKind.RESERVE, bank.currency, house.code)
            clearing = AccountRef(house.code, AccountKind.CLEARING, bank.currency, bank.code)
            add(reserve, clearing, AccountRef(house.code, AccountKind.CASH, bank.currency))
            funding.append((reserve, clearing, d.opening_minor(bank.currency, d.reserve_major)))
        return refs, funding

    def ensure_network(self, session: Session) -> int:
        """Create any missing bank accounts and fund them. Safe to run again. Returns how many
        accounts were created. The caller writes the audit event."""
        created = 0
        refs, funding = self._infrastructure()
        for ref in refs:
            created += int(self.ledger.open_account(session, ref)[1])
        for asset, liability, amount in funding:
            if self._is_unfunded(session, asset):
                self._fund_pair(session, asset, liability, amount)
        created += self._ensure_customers(session)
        return created

    def _is_unfunded(self, session: Session, ref: AccountRef) -> bool:
        account = self.ledger.require(session, ref)
        has_entry = session.execute(
            select(LedgerEntry.id).where(LedgerEntry.account_id == account.id).limit(1)
        ).first()
        return has_entry is None

    def _fund_pair(
        self, session: Session, asset: AccountRef, liability: AccountRef, amount: int
    ) -> None:
        ccy = asset.currency
        cash_asset = AccountRef(asset.bank, AccountKind.CASH, ccy)
        cash_liability = AccountRef(liability.bank, AccountKind.CASH, ccy)
        self.ledger.open_account(session, cash_asset)
        self.ledger.open_account(session, cash_liability)
        pairs = (
            make_journal(
                "Opening: fund the account",
                [(asset, Side.DEBIT, amount), (cash_asset, Side.CREDIT, amount)],
            ),
            make_journal(
                "Opening: record the deposit",
                [(cash_liability, Side.DEBIT, amount), (liability, Side.CREDIT, amount)],
            ),
        )  # fmt: skip
        for journal in pairs:
            self.ledger.post(session, journal, transfer_id=None, kind="OPENING")

    def _ensure_customers(self, session: Session) -> int:
        from app.core.demo import PARENT_ID

        household = PARENT_ID if session.get(User, PARENT_ID) is not None else None
        created = 0
        for demo in self.directory.demo_accounts:
            if demo.owner is not None and household is None:
                continue  # the demo household does not exist yet; a later run adds these
            ref = AccountRef(demo.bank, AccountKind.CUSTOMER, demo.currency, number=demo.number)
            owner = household if demo.owner is not None else None
            _, is_new = self.ledger.open_account(
                session, ref, holder=demo.holder, label=demo.label, owner_id=owner
            )
            if not is_new:
                continue
            created += 1
            if demo.opening_minor > 0:
                cash = AccountRef(demo.bank, AccountKind.CASH, demo.currency)
                self.ledger.open_account(session, cash)
                opening = make_journal(
                    f"Opening balance for {demo.label}",
                    [
                        (cash, Side.DEBIT, demo.opening_minor),
                        (ref, Side.CREDIT, demo.opening_minor),
                    ],
                )
                self.ledger.post(session, opening, transfer_id=None, kind="OPENING")
        return created

    def is_ready(self, session: Session) -> bool:
        return self.ledger.find(session, self._first_customer_ref()) is not None

    def _first_customer_ref(self) -> AccountRef:
        demo = self.directory.demo_accounts[0]
        return AccountRef(demo.bank, AccountKind.CUSTOMER, demo.currency, number=demo.number)

    # --- lookups ----------------------------------------------------------------------------------
    def _customer_by_id_or_number(self, session: Session, value: str) -> BankAccount | None:
        found = session.get(BankAccount, value)
        if found is None:
            found = session.execute(
                select(BankAccount).where(
                    BankAccount.number == value, BankAccount.kind == AccountKind.CUSTOMER.value
                )
            ).scalar_one_or_none()
        return found if found is not None and found.kind == AccountKind.CUSTOMER.value else None

    def _load(self, session: Session, actor: Actor, transfer_id: str) -> BankTransfer:
        transfer = session.get(BankTransfer, transfer_id)
        if transfer is None or not actor.can_see_owner(transfer.owner_id):
            raise errors.NotFound("Transfer not found.")
        return transfer

    def _account(self, session: Session, account_id: str) -> BankAccount:
        account = session.get(BankAccount, account_id)
        if account is None:
            raise errors.Internal("A transfer points at a missing account.")
        return account

    def _bank_name(self, code: str) -> str:
        if code in self.directory.banks:
            return self.directory.banks[code].name
        if code in self.directory.clearing:
            return self.directory.clearing[code].name
        return code

    # --- creating a transfer ----------------------------------------------------------------------
    def create_transfer(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        *,
        source: str,
        destination: str,
        amount: Money,
        rail: str | None,
        charge_code: str | None,
        reference: str,
    ) -> BankTransfer:
        """Plan a transfer and store it as PENDING_CONFIRMATION. No money moves yet."""
        authorize(actor, Perm.BANK_TRANSFER)
        src = self._customer_by_id_or_number(session, source)
        if src is None or src.owner_id is None or not actor.can_see_owner(src.owner_id):
            raise errors.NotFound("Source account not found.")
        dst = self._customer_by_id_or_number(session, destination)
        if dst is None:
            raise errors.NotFound("Destination account not found.")
        now = self._clock.now()
        if is_sanctions_hit(rules, dst.holder_name):
            self._audit.append(
                session,
                actor_type=actor.audit_type,
                actor_id=actor.user_id,
                action="bank.transfer_blocked",
                amount_minor=amount.amount_minor,
                currency=amount.currency,
                decision=Decision.BLOCKED,
                reason_code="SANCTIONS_HIT",
                detail="Beneficiary matched the mock sanctions screening",
            )
            raise errors.SanctionsHit(
                "The beneficiary matched mock sanctions screening (simulated).", persist=True
            )
        scenario = scenario_for(rules, dst.holder_name)
        try:
            plan, uetr = self._plan(rules, src, dst, amount, rail, charge_code, scenario)
        except RailRejected as exc:
            raise errors.ValidationFailed(str(exc), extra={"reason": exc.code}) from exc
        except EngineError as exc:
            raise errors.ValidationFailed(str(exc)) from exc
        if plan.kind == INTERNATIONAL:
            usd = usd_equivalent_minor(rules, plan.credit)
            if evaluate_limits(rules, usd, 0) is not None:
                raise errors.LimitExceeded(
                    "Above the sandbox per-transaction cap (not a legal limit)."
                )
        transfer = BankTransfer(
            id=new_id("btr"),
            owner_id=src.owner_id,
            created_by=actor.user_id,
            kind=plan.kind,
            rail=plan.rail,
            status=BankTransferStatus.PENDING_CONFIRMATION.value,
            source_account_id=src.id,
            destination_account_id=dst.id,
            debit_minor=plan.debit.amount_minor,
            debit_currency=plan.debit.currency,
            credit_minor=plan.credit.amount_minor,
            credit_currency=plan.credit.currency,
            fee_minor=plan.fee.amount_minor,
            reference=reference,
            uetr=uetr,
            scenario=scenario.value,
            plan_json=plan.to_dict(),
            plan_hash=plan.plan_hash,
            next_step=0,
            created_at=now,
            updated_at=now,
        )
        session.add(transfer)
        session.flush()
        self._event(
            session,
            transfer,
            "PLAN",
            src.bank_code,
            "created",
            "Transfer planned. Waiting for MFA confirmation.",
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank.transfer_created",
            payment_id=transfer.id,
            amount_minor=plan.debit.amount_minor,
            currency=plan.debit.currency,
            detail=f"{plan.kind} {plan.rail} {src.bank_code} to {dst.bank_code}",
            input_hash=plan.plan_hash,
        )
        return transfer

    def _plan(
        self,
        rules: Rules,
        src: BankAccount,
        dst: BankAccount,
        amount: Money,
        rail: str | None,
        charge_code: str | None,
        scenario: Scenario,
    ) -> tuple[TransferPlan, str | None]:
        d = self.directory
        src_bank, dst_bank = d.bank(src.bank_code), d.bank(dst.bank_code)
        source_ref, dest_ref = ref_of(src), ref_of(dst)
        slow = d.slow_factor if scenario is Scenario.SLOW else 1
        if src_bank.role == AD_BANK and dst_bank.role == HOST_BANK:
            if amount.currency != dst.currency:
                raise RailRejected(
                    "CURRENCY_MISMATCH",
                    f"Amount is in {amount.currency}; the beneficiary holds {dst.currency}.",
                )
            terms = next(
                (t for t in rules.provider_terms() if t.provider_id == src_bank.provider_id), None
            )
            if terms is None:
                raise RailRejected(
                    "NO_PROVIDER_TERMS", "No pricing terms for the originating bank."
                )
            requested = ChargeCode(charge_code) if charge_code else terms.default_charge_code
            result = compute_provider_result(
                target=amount,
                mid_rate=rules.mid_rate(amount.currency),
                terms=terms,
                requested_charge_code=requested,
                params=rules.engine_params(),
            )  # fmt: skip
            delays = scale_delays(d.international_delays, slow)
            plan = plan_international(
                source=source_ref,
                destination=dest_ref,
                correspondent=d.correspondent.code,
                result=result,
                delays=(delays[0], delays[1], delays[2]),
            )
            return plan, str(uuid.uuid4())
        if src_bank.country != dst_bank.country or src.currency != dst.currency:
            raise errors.RouteNotSupported(
                "Only Bangladesh-bank to foreign-bank transfers (BDT out) and transfers inside "
                "one country are simulated."
            )
        if src_bank.code == dst_bank.code:
            terms_rail = on_us_terms(src.currency, scale_delays(d.on_us_delays, slow))
            return plan_national(
                source=source_ref,
                destination=dest_ref,
                amount=amount,
                rail=terms_rail,
                clearing_house=None,
            ), None
        house = d.clearing_house_for(src_bank)
        rails = d.rails_for(src.currency)
        chosen = rails.get(rail) if rail and rail != ON_US else None
        if rail and chosen is None:
            raise RailRejected("UNKNOWN_RAIL", f"No rail called {rail} for {src.currency}.")
        if chosen is None:
            options = eligible_rails(rails, amount)
            if not options:
                raise RailRejected("NO_RAIL", "No rail accepts this amount.")
            chosen = options[0]
        chosen = dataclasses.replace(chosen, delays=scale_delays(chosen.delays, slow))
        return (
            plan_national(
                source=source_ref,
                destination=dest_ref,
                amount=amount,
                rail=chosen,
                clearing_house=house.code if house else None,
            ),
            None,
        )

    # --- confirming and cancelling ----------------------------------------------------------------
    def confirm(
        self,
        session: Session,
        actor: Actor,
        transfer_id: str,
        mfa_proof_raw: str | None,
    ) -> BankTransfer:
        """A human with a fresh MFA proof for THIS transfer reserves the funds and starts it."""
        authorize(actor, Perm.BANK_TRANSFER)
        transfer = self._load(session, actor, transfer_id)
        if transfer.status != BankTransferStatus.PENDING_CONFIRMATION.value:
            raise errors.InvalidState("Only a transfer waiting for confirmation can be confirmed.")
        now = self._clock.now()
        proof = auth.find_valid_mfa_proof(
            session,
            raw=mfa_proof_raw,
            user_id=actor.user_id,
            scope=MFA_SCOPE,
            subject_id=transfer.id,
            now=now,
        )  # fmt: skip
        if proof is None:
            raise errors.MfaRequired("A fresh MFA proof for this transfer is required.")
        owner = session.get(User, transfer.owner_id)
        if transfer.kind == INTERNATIONAL and (owner is None or owner.kyc_status != "VERIFIED"):
            raise errors.KycNotVerified(
                "KYC must be verified before an international transfer (simulated)."
            )
        plan = TransferPlan.from_dict(transfer.plan_json)
        try:
            self.ledger.post(
                session, plan.hold, transfer_id=transfer.id, kind="HOLD", stage="HOLD", seq=0
            )
        except LedgerError as exc:
            raise errors.InsufficientFunds(
                "The source account does not hold enough money for this transfer and its fees."
            ) from exc
        self._mark_proof_used(proof, now)
        transfer.status = BankTransferStatus.ACCEPTED.value
        transfer.confirmed_at = now
        transfer.next_step_at = now + timedelta(seconds=plan.steps[0].delay_seconds)
        transfer.updated_at = now
        self._event(
            session,
            transfer,
            "HOLD",
            transfer_bank(plan),
            "accepted",
            "Funds reserved. The payment order is accepted.",
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank.transfer_confirmed",
            payment_id=transfer.id,
            amount_minor=transfer.debit_minor,
            currency=transfer.debit_currency,
            decision=Decision.APPROVED,
            reason_code=auth.proof_reference(proof),
            detail=f"{transfer.kind} {transfer.rail}: funds reserved",
            input_hash=transfer.plan_hash,
        )
        return transfer

    def _mark_proof_used(self, proof: MfaProof, now: datetime) -> None:
        proof.used_at = now

    def cancel(self, session: Session, actor: Actor, transfer_id: str) -> BankTransfer:
        authorize(actor, Perm.BANK_TRANSFER)
        transfer = self._load(session, actor, transfer_id)
        if transfer.status != BankTransferStatus.PENDING_CONFIRMATION.value:
            raise errors.InvalidState("Only a transfer waiting for confirmation can be cancelled.")
        now = self._clock.now()
        transfer.status = BankTransferStatus.CANCELLED.value
        transfer.updated_at = now
        self._event(
            session,
            transfer,
            "PLAN",
            "",
            "cancelled",
            "Cancelled before confirmation. Nothing was reserved.",
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank.transfer_cancelled",
            payment_id=transfer.id,
            amount_minor=transfer.debit_minor,
            currency=transfer.debit_currency,
            decision=Decision.REJECTED,
            detail="Cancelled by the payer",
        )
        return transfer

    # --- the simulator: one hop at a time ---------------------------------------------------------
    def due_ids(self, session: Session, now: datetime, limit: int = 50) -> list[str]:
        rows = session.execute(
            select(BankTransfer.id)
            .where(BankTransfer.status.in_(OPEN_STATES), BankTransfer.next_step_at <= now)
            .order_by(BankTransfer.next_step_at)
            .limit(limit)
        ).scalars()
        return list(rows)

    def run_next_step(
        self,
        session: Session,
        transfer_id: str,
        *,
        actor: Actor = SYSTEM_ACTOR,
        force_fail: bool = False,
        only_if_due: bool = False,
    ) -> BankTransfer:
        transfer = session.get(BankTransfer, transfer_id)
        if transfer is None:
            raise errors.NotFound("Transfer not found.")
        if transfer.status not in OPEN_STATES:
            raise errors.InvalidState("This transfer is not in flight.")
        due_at = transfer.next_step_at
        if only_if_due and (due_at is None or due_at > self._clock.now()):
            # The worker saw this hop as due, but a reviewer ran it first: never run the next early.
            raise errors.InvalidState("The next hop is not due yet.")
        plan = TransferPlan.from_dict(transfer.plan_json)
        index = transfer.next_step
        step = plan.steps[index]
        last = index == len(plan.steps) - 1
        if force_fail:
            return self._unwind(session, transfer, plan, actor, "SANDBOX_FORCED")
        if last and transfer.scenario == Scenario.FAIL.value:
            return self._unwind(session, transfer, plan, actor, "BENEFICIARY_REJECTED")
        try:
            for journal in step.journals:
                self.ledger.post(
                    session,
                    journal,
                    transfer_id=transfer.id,
                    kind="STEP",
                    stage=step.stage,
                    seq=index + 1,
                )
        except LedgerError as exc:
            return self._unwind(session, transfer, plan, actor, exc.code)
        now = self._clock.now()
        transfer.next_step = index + 1
        transfer.updated_at = now
        message = self._message(session, transfer, plan, index)
        self._event(session, transfer, step.stage, step.bank, "step_done", step.summary, message)
        if last:
            transfer.status = BankTransferStatus.SETTLED.value
            transfer.settled_at = now
            transfer.next_step_at = None
            action, detail = "bank.transfer_settled", f"{step.summary}: settled"
        else:
            transfer.status = BankTransferStatus.IN_TRANSIT.value
            transfer.next_step_at = now + timedelta(seconds=plan.steps[index + 1].delay_seconds)
            action, detail = "bank.transfer_step", step.summary
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action=action,
            payment_id=transfer.id,
            amount_minor=transfer.credit_minor if last else None,
            currency=transfer.credit_currency if last else None,
            reason_code=step.stage,
            detail=detail[:240],
        )
        return transfer

    def _unwind(
        self, session: Session, transfer: BankTransfer, plan: TransferPlan, actor: Actor, code: str
    ) -> BankTransfer:
        """Post the exact opposite of everything posted so far, newest first."""
        now = self._clock.now()
        seq = 100
        try:
            for step in reversed(plan.steps[: transfer.next_step]):
                for journal in reversed(step.journals):
                    seq += 1
                    self.ledger.post(
                        session,
                        journal.reversed(),
                        transfer_id=transfer.id,
                        kind="REVERSAL",
                        stage=step.stage,
                        seq=seq,
                    )
            self.ledger.post(
                session,
                plan.hold.reversed(),
                transfer_id=transfer.id,
                kind="REVERSAL",
                stage="HOLD",
                seq=seq + 1,
            )
        except LedgerError as exc:  # a reversal restores balances, so this would be a bug
            raise errors.Internal("The sandbox could not unwind a transfer.") from exc
        reason = FAILURE_TEXT.get(code, "The transfer failed (simulated).")
        transfer.status = BankTransferStatus.RETURNED.value
        transfer.failure_reason = reason
        transfer.next_step_at = None
        transfer.updated_at = now
        bank = plan.steps[min(transfer.next_step, len(plan.steps) - 1)].bank
        self._event(
            session,
            transfer,
            "RETURN",
            bank,
            "returned",
            f"{reason} The money was returned in full.",
        )
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="bank.transfer_returned",
            payment_id=transfer.id,
            amount_minor=transfer.debit_minor,
            currency=transfer.debit_currency,
            decision=Decision.REJECTED,
            reason_code=code,
            detail=reason[:240],
        )
        return transfer

    def advance_due(self, db: Any) -> int:
        """Run every hop whose time has come, each in its own transaction. Returns the count."""
        with db.read() as session:
            ids = self.due_ids(session, self._clock.now())
        done = 0
        for transfer_id in ids:
            try:
                with db.write() as session:
                    self.run_next_step(session, transfer_id, only_if_due=True)
                done += 1
            except errors.ApiError:
                continue
        return done

    def sandbox_control(
        self, session: Session, actor: Actor, transfer_id: str, outcome: str
    ) -> BankTransfer:
        """Reviewer only: run the next hop now, or make the transfer fail to show the return."""
        authorize(actor, Perm.SANDBOX_CONTROL)
        return self.run_next_step(session, transfer_id, actor=actor, force_fail=outcome == "fail")

    # --- events and messages ----------------------------------------------------------------------
    def _event(
        self,
        session: Session,
        transfer: BankTransfer,
        stage: str,
        bank: str,
        event: str,
        note: str,
        message: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            BankTransferEvent(
                transfer_id=transfer.id,
                at=self._clock.now(),
                stage=stage,
                bank_code=bank,
                event=event,
                note=note[:240],
                message_json=message,
            )
        )

    def _message(
        self, session: Session, transfer: BankTransfer, plan: TransferPlan, index: int
    ) -> dict[str, Any]:
        step = plan.steps[index]
        following = plan.steps[index + 1].bank if index + 1 < len(plan.steps) else None
        base: dict[str, Any] = {
            "simulated": True,
            "type": step.message,
            "from": step.bank,
            "to": following,
            "reference": transfer.reference,
        }
        if transfer.kind == INTERNATIONAL and step.message == "MT103":
            src = self._account(session, transfer.source_account_id)
            dst = self._account(session, transfer.destination_account_id)
            instructed = plan.figures["instructed"]
            country = self.directory.bank(dst.bank_code).country
            base.update(
                build_instruction_preview(
                    payment_id=transfer.id,
                    uetr=transfer.uetr,
                    value_date=None,
                    amount=Money(int(instructed["amount_minor"]), str(instructed["currency"])),
                    ordering_name=src.holder_name,
                    ordering_address="Dhaka, BD (synthetic)",
                    receiving_bic=dst.bank_code,
                    beneficiary_name=dst.holder_name,
                    beneficiary_account_masked=mask_account(dst.number, country),
                    remittance=transfer.reference,
                    charge_code=ChargeCode(str(plan.figures["charge_code"])),
                )
            )
        else:
            base["amount"] = plan.credit.to_dict()
        return base

    # --- views ------------------------------------------------------------------------------------
    def account_view(self, account: BankAccount) -> dict[str, Any]:
        bank = self.directory.banks.get(account.bank_code)
        return {
            "id": account.id,
            "bank_code": account.bank_code,
            "bank_name": self._bank_name(account.bank_code),
            "country": bank.country if bank else None,
            "kind": account.kind,
            "number": account.number,
            "holder": account.holder_name,
            "label": account.label,
            "currency": account.currency,
            "balance": Money(account.balance_minor, account.currency).to_dict(),
            "household": account.owner_id is not None,
            "simulated": True,
        }

    def list_accounts(self, session: Session, actor: Actor) -> list[dict[str, Any]]:
        authorize(actor, Perm.BANK_READ)
        query = select(BankAccount).where(BankAccount.kind == AccountKind.CUSTOMER.value)
        if actor.owner_id is not None:
            query = query.where(BankAccount.owner_id == actor.owner_id)
        rows = session.execute(query.order_by(BankAccount.bank_code, BankAccount.number)).scalars()
        return [self.account_view(a) for a in rows]

    def household_totals(
        self, session: Session, actor: Actor, rules: Rules
    ) -> dict[str, Any] | None:
        """The household's money in every currency, with an indicative BDT equivalent.

        Converted at the synthetic mid-market rates, so it is a rough guide and not a live rate.
        The reviewer sees every household, so a single total would mean nothing: None.
        """
        authorize(actor, Perm.BANK_READ)
        if actor.owner_id is None:
            return None
        rows = session.execute(
            select(BankAccount).where(
                BankAccount.kind == AccountKind.CUSTOMER.value,
                BankAccount.owner_id == actor.owner_id,
            )
        ).scalars()
        sums: dict[str, list[int]] = {}
        for account in rows:
            entry = sums.setdefault(account.currency, [0, 0])
            entry[0] += account.balance_minor
            entry[1] += 1
        lines = []
        total_bdt = 0
        for currency in sorted(sums, key=lambda c: (c != "BDT", c)):
            balance, count = sums[currency]
            if currency == "BDT":
                bdt = balance
            else:
                rate = rules.mid_rate(currency)
                bdt = round_half_up(fx.foreign_to_bdt_minor(balance, currency, rate))
            total_bdt += bdt
            lines.append(
                {
                    "currency": currency,
                    "accounts": count,
                    "balance": Money(balance, currency).to_dict(),
                    "bdt_equivalent": Money(bdt, "BDT").to_dict(),
                }
            )
        return {
            "by_currency": lines,
            "bdt_total": Money(total_bdt, "BDT").to_dict(),
            "note": "Converted at synthetic mid-market rates. Not a live FX feed. "
            "Indicative. Confirm with your AD bank.",
        }

    def list_beneficiaries(self, session: Session, actor: Actor) -> list[dict[str, Any]]:
        """Every customer account a transfer could go to (synthetic directory)."""
        authorize(actor, Perm.BANK_READ)
        rows = session.execute(
            select(BankAccount)
            .where(BankAccount.kind == AccountKind.CUSTOMER.value)
            .order_by(BankAccount.currency, BankAccount.holder_name)
        ).scalars()
        return [{k: v for k, v in self.account_view(a).items() if k != "balance"} for a in rows]

    def list_transfers(
        self, session: Session, actor: Actor, limit: int = 20
    ) -> list[dict[str, Any]]:
        authorize(actor, Perm.BANK_READ)
        query = select(BankTransfer).order_by(BankTransfer.created_at.desc()).limit(limit)
        if actor.owner_id is not None:
            query = query.where(BankTransfer.owner_id == actor.owner_id)
        return [self.transfer_view(session, t) for t in session.execute(query).scalars()]

    def get_transfer(self, session: Session, actor: Actor, transfer_id: str) -> dict[str, Any]:
        authorize(actor, Perm.BANK_READ)
        return self.transfer_view(session, self._load(session, actor, transfer_id), detail=True)

    def statement(self, session: Session, actor: Actor, account_id: str) -> dict[str, Any]:
        authorize(actor, Perm.BANK_READ)
        account = session.get(BankAccount, account_id)
        if account is None or account.kind != AccountKind.CUSTOMER.value:
            raise errors.NotFound("Account not found.")
        if account.owner_id is None or not actor.can_see_owner(account.owner_id):
            raise errors.NotFound("Account not found.")
        return {
            "account": self.account_view(account),
            "entries": self.ledger.statement(session, account.id),
            "simulated": True,
        }

    def transfer_view(
        self, session: Session, transfer: BankTransfer, *, detail: bool = False
    ) -> dict[str, Any]:
        plan = TransferPlan.from_dict(transfer.plan_json)
        src = self._account(session, transfer.source_account_id)
        dst = self._account(session, transfer.destination_account_id)
        status = BankTransferStatus(transfer.status)
        done = transfer.next_step if status is not BankTransferStatus.RETURNED else 0
        view: dict[str, Any] = {
            "id": transfer.id,
            "status": transfer.status,
            "kind": transfer.kind,
            "rail": transfer.rail,
            "reference": transfer.reference,
            "uetr": transfer.uetr,
            "source": self.account_view(src),
            "destination": {k: v for k, v in self.account_view(dst).items() if k != "balance"},
            "debit": plan.debit.to_dict(),
            "credit": plan.credit.to_dict(),
            "fee": plan.fee.to_dict(),
            "figures": dict(plan.figures),
            "plan_hash": transfer.plan_hash,
            "steps": [
                {
                    "stage": s.stage,
                    "bank": s.bank,
                    "bank_name": self._bank_name(s.bank),
                    "summary": s.summary,
                    "delay_seconds": s.delay_seconds,
                    "done": i < done and status is not BankTransferStatus.RETURNED,
                    "message": s.message,
                }
                for i, s in enumerate(plan.steps)
            ],
            "next_step_at": iso_utc(transfer.next_step_at) if transfer.next_step_at else None,
            "failure_reason": transfer.failure_reason,
            "created_at": iso_utc(transfer.created_at),
            "confirmed_at": iso_utc(transfer.confirmed_at) if transfer.confirmed_at else None,
            "settled_at": iso_utc(transfer.settled_at) if transfer.settled_at else None,
            "blockers": self._blockers(session, transfer, src),
            "simulated": True,
            "note": "Simulated. No real bank is contacted and no real money moves.",
        }
        if detail:
            view["events"] = self._events(session, transfer.id)
            view["journals"] = self._journals(session, transfer.id)
        return view

    def _blockers(
        self, session: Session, transfer: BankTransfer, src: BankAccount
    ) -> list[dict[str, str]]:
        if transfer.status != BankTransferStatus.PENDING_CONFIRMATION.value:
            return []
        found = []
        owner = session.get(User, transfer.owner_id)
        if transfer.kind == INTERNATIONAL and (owner is None or owner.kyc_status != "VERIFIED"):
            found.append(
                {"code": "KYC_NOT_VERIFIED", "message": "KYC is not verified (simulated)."}
            )
        if src.balance_minor < transfer.debit_minor:
            found.append(
                {
                    "code": "INSUFFICIENT_FUNDS",
                    "message": "The source account does not hold enough.",
                }
            )
        return found

    def _events(self, session: Session, transfer_id: str) -> list[dict[str, Any]]:
        rows = session.execute(
            select(BankTransferEvent)
            .where(BankTransferEvent.transfer_id == transfer_id)
            .order_by(BankTransferEvent.id)
        ).scalars()
        return [
            {
                "at": iso_utc(e.at),
                "stage": e.stage,
                "bank_code": e.bank_code,
                "bank_name": self._bank_name(e.bank_code) if e.bank_code else "",
                "event": e.event,
                "note": e.note,
                "message": e.message_json,
            }
            for e in rows
        ]

    def _journals(self, session: Session, transfer_id: str) -> list[dict[str, Any]]:
        journals = session.execute(
            select(LedgerJournal)
            .where(LedgerJournal.transfer_id == transfer_id)
            .order_by(LedgerJournal.posted_at, LedgerJournal.id)
        ).scalars()
        out = []
        for journal in journals:
            lines = session.execute(
                select(LedgerEntry, BankAccount)
                .join(BankAccount, BankAccount.id == LedgerEntry.account_id)
                .where(LedgerEntry.journal_id == journal.id)
                .order_by(LedgerEntry.id)
            ).all()
            out.append(
                {
                    "id": journal.id,
                    "kind": journal.kind,
                    "stage": journal.stage,
                    "memo": journal.memo,
                    "posted_at": iso_utc(journal.posted_at),
                    "lines": [
                        {
                            "side": entry.side,
                            "bank": self._bank_name(account.bank_code),
                            "account": account.kind
                            + (f" ({account.counterparty})" if account.counterparty else "")
                            + (f" {account.number}" if account.number else ""),
                            "amount": Money(entry.amount_minor, entry.currency).to_dict(),
                        }
                        for entry, account in lines
                    ],
                }
            )
        return out

    def network_overview(self, session: Session) -> dict[str, Any]:
        trial = self.ledger.trial_balance(session)
        mirrors = self.ledger.mirror_report(session)
        mismatched = self.ledger.balances_that_do_not_match_entries(session)
        return {
            "simulated": True,
            "directory": self.directory.to_api(),
            "trial_balance": trial,
            "mirror_accounts": [
                {
                    **m,
                    "holder_bank_name": self._bank_name(m["holder_bank"]),
                    "other_name": self._bank_name(m["other_institution"]),
                    "balance": Money(m["holder_balance_minor"], m["currency"]).to_dict(),
                }
                for m in mirrors
            ],
            "accounts_not_matching_entries": len(mismatched),
            "all_ok": all(t["balanced"] for t in trial.values())
            and all(m["reconciled"] for m in mirrors)
            and not mismatched,
        }


def transfer_bank(plan: TransferPlan) -> str:
    return plan.source.bank
