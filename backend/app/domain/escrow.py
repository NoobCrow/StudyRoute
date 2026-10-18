"""Programmable escrow on the sandbox chain: tuition and living costs released on a schedule.

A parent PLANS an escrow (nothing happens yet), then a human CONFIRMS it with a fresh MFA proof
for that exact escrow. Confirming runs three transactions on the sandbox chain: the bank issues
a tokenised deposit to the parent (against a simulated debit), the parent allows the escrow to
take it, and the escrow locks it in tranches. From then on the contract enforces the rules:
each tranche is paid on its date, the parent can pay one early or take back what is not yet due
(both need MFA), and the bank's compliance reviewer can freeze an escrow, which only stops
movement. The AI has no escrow permission at all.

Every state change writes ONE audit event in the same database transaction as the chain log.
Only hashes go on the chain: no names, account numbers or payment references.

Nothing here is real. The chain is a simulation, the tokens are not money, and no bank is
contacted.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.service import AuditService
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import canonical_json, sha256_hex
from app.core.ids import new_id
from app.domain import auth
from app.domain.chain_service import (
    BANK,
    COMPLIANCE,
    ESCROW,
    ChainService,
    TxRecord,
    iso_utc_from_epoch,
    recipient_wallet,
    token_label,
    user_wallet,
)
from app.domain.compliance import is_sanctions_hit
from app.domain.constants import ActorType, Decision, EscrowStatus, Purpose
from app.domain.limits import evaluate_limits, usd_equivalent_minor
from app.domain.rbac import Actor, Perm, authorize
from app.domain.recipients import RecipientService
from app.domain.rules import Rules
from app.engine.escrow_schedule import ScheduleError, build_schedule, release_timestamp
from app.engine.money import CURRENCY_EXPONENTS, Money
from app.engine.validators import is_valid_swift_reference
from app.models import Escrow, MfaProof, Recipient, User

MFA_CONFIRM = "confirm_escrow"
MFA_RELEASE = "release_escrow"
MFA_CANCEL = "cancel_escrow"

CHAIN_STATUS = {0: "NONE", 1: "ACTIVE", 2: "FROZEN", 3: "COMPLETED", 4: "CANCELLED"}
TRANCHE_STATE = {0: "LOCKED", 1: "RELEASED", 2: "REFUNDED"}
MAX_REFERENCE = 70
MAX_REASON = 120


def _hash32(text: str) -> str:
    """A bytes32 for the chain: the hash of a private value, never the value."""
    return "0x" + sha256_hex(text)


class EscrowService:
    def __init__(
        self, clock: Clock, audit: AuditService, recipients: RecipientService, chain: ChainService
    ) -> None:
        self._clock = clock
        self._audit = audit
        self._recipients = recipients
        self._chain = chain

    # --- loading -------------------------------------------------------------------------------
    def _load(self, session: Session, actor: Actor, escrow_id: str) -> Escrow:
        row = session.get(Escrow, escrow_id)
        if row is None or not actor.can_see_owner(row.owner_id):
            raise errors.NotFound("Escrow not found.")
        return row

    def _on_chain(self, row: Escrow) -> int:
        if row.status != EscrowStatus.ON_CHAIN.value or row.chain_escrow_id is None:
            raise errors.InvalidState("This escrow is not on the chain yet.")
        return int(row.chain_escrow_id)

    # --- planning ------------------------------------------------------------------------------
    def plan(
        self,
        session: Session,
        actor: Actor,
        rules: Rules,
        *,
        recipient_id: str,
        purpose: str,
        total_minor: int,
        currency: str,
        tranches: int,
        first_release: date,
        cadence: str,
        reference: str,
    ) -> Escrow:
        """Work out the schedule and store it as PENDING_CONFIRMATION. Nothing moves yet."""
        authorize(actor, Perm.ESCROW_WRITE)
        recipient = self._recipients.get_owned(session, actor, recipient_id)
        corridor = rules.open_corridor(recipient.country)
        if currency != corridor.currency:
            raise errors.ValidationFailed(
                f"Payments to {corridor.name} are made in {corridor.currency}."
            )
        if purpose not in {p.value for p in Purpose}:
            raise errors.ValidationFailed("Purpose must be TUITION or LIVING.")
        reference = reference.strip()
        if not 1 <= len(reference) <= MAX_REFERENCE or not is_valid_swift_reference(reference):
            raise errors.ValidationFailed(
                f"The reference must be 1 to {MAX_REFERENCE} letters, digits or / - ? : ( ) . , ' +"
            )
        now = self._clock.now()
        if not now.date() <= first_release <= now.date() + timedelta(days=800):
            raise errors.ValidationFailed("The first release date must be today or later.")
        if is_sanctions_hit(rules, recipient.display_name):
            self._audit.append(
                session,
                actor_type=actor.audit_type,
                actor_id=actor.user_id,
                action="escrow.blocked",
                amount_minor=total_minor,
                currency=corridor.currency,
                recipient_id=recipient.id,
                decision=Decision.BLOCKED,
                reason_code="SANCTIONS_HIT",
                detail="Beneficiary matched the mock sanctions screening",
            )
            raise errors.SanctionsHit(
                "The beneficiary matched mock sanctions screening (simulated).", persist=True
            )
        try:
            schedule = build_schedule(total_minor, tranches, first_release, cadence)
        except ScheduleError as exc:
            raise errors.ValidationFailed(str(exc)) from exc
        total = Money(total_minor, corridor.currency)
        if evaluate_limits(rules, usd_equivalent_minor(rules, total), 0) is not None:
            raise errors.LimitExceeded("Above the sandbox per-transaction cap (not a legal limit).")
        plan_json = [
            {
                "index": t.index,
                "amount_minor": t.amount_minor,
                "release_on": t.release_on.isoformat(),
            }
            for t in schedule
        ]
        plan_hash = sha256_hex(
            canonical_json(
                {
                    "recipient_id": recipient.id,
                    "purpose": purpose,
                    "currency": corridor.currency,
                    "total_minor": total_minor,
                    "cadence": cadence,
                    "reference": reference,
                    "tranches": plan_json,
                }
            )
        )
        row = Escrow(
            id=new_id("esc"),
            owner_id=recipient.owner_id,
            created_by=actor.user_id,
            recipient_id=recipient.id,
            purpose=purpose,
            currency=corridor.currency,
            total_minor=total_minor,
            cadence=cadence if tranches > 1 else "ONCE",
            reference=reference,
            plan_json=plan_json,
            plan_hash=plan_hash,
            status=EscrowStatus.PENDING_CONFIRMATION.value,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.planned",
            payment_id=row.id,
            amount_minor=total_minor,
            currency=corridor.currency,
            recipient_id=recipient.id,
            detail=f"{purpose} escrow planned: {tranches} tranche(s), nothing locked yet",
            input_hash=plan_hash,
        )
        return row

    def abandon(self, session: Session, actor: Actor, escrow_id: str) -> Escrow:
        """Drop a plan that was never confirmed. Nothing was locked, so no MFA is needed."""
        authorize(actor, Perm.ESCROW_WRITE)
        row = self._load(session, actor, escrow_id)
        if row.status != EscrowStatus.PENDING_CONFIRMATION.value:
            raise errors.InvalidState("Only a plan waiting for confirmation can be dropped.")
        row.status = EscrowStatus.ABANDONED.value
        row.updated_at = self._clock.now()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.abandoned",
            payment_id=row.id,
            amount_minor=row.total_minor,
            currency=row.currency,
            decision=Decision.REJECTED,
            detail="Plan dropped before confirmation. Nothing was locked",
        )
        return row

    # --- the human steps (MFA) --------------------------------------------------------------------
    def _proof(
        self, session: Session, actor: Actor, scope: str, row: Escrow, raw: str | None
    ) -> MfaProof:
        proof = auth.find_valid_mfa_proof(
            session,
            raw=raw,
            user_id=actor.user_id,
            scope=scope,
            subject_id=row.id,
            now=self._clock.now(),
        )
        if proof is None:
            raise errors.MfaRequired("A fresh MFA proof for this escrow is required.")
        return proof

    def confirm(
        self, session: Session, actor: Actor, rules: Rules, escrow_id: str, mfa_raw: str | None
    ) -> Escrow:
        """A human with a fresh MFA proof locks the funds in the escrow contract."""
        authorize(actor, Perm.ESCROW_WRITE)
        row = self._load(session, actor, escrow_id)
        if row.status != EscrowStatus.PENDING_CONFIRMATION.value:
            raise errors.InvalidState("Only a plan waiting for confirmation can be confirmed.")
        proof = self._proof(session, actor, MFA_CONFIRM, row, mfa_raw)
        owner = session.get(User, row.owner_id)
        if owner is None or owner.kyc_status != "VERIFIED":
            raise errors.KycNotVerified("KYC must be verified before locking funds (simulated).")
        recipient = session.get(Recipient, row.recipient_id)
        if recipient is None:
            raise errors.NotFound("Recipient not found.")
        rules.open_corridor(recipient.country)
        if is_sanctions_hit(rules, recipient.display_name):
            raise errors.SanctionsHit(
                "The beneficiary matched mock sanctions screening (simulated)."
            )

        chain = self._chain
        chain.ready(session)
        token_addr = chain.ensure_token(
            session, row.currency, CURRENCY_EXPONENTS[row.currency], actor.user_id
        )
        payer = user_wallet(row.owner_id)
        txs: list[TxRecord] = []

        def send(contract: str, function: str, args: list[Any], caller: str) -> TxRecord:
            tx = chain.send(
                session, contract=contract, function=function, args=args, caller=caller,
                actor_id=actor.user_id, ref=row.id,
            )  # fmt: skip
            txs.append(tx)
            return tx

        escrow_addr = chain.address(session, ESCROW)
        send(token_label(row.currency), "mint", [chain.wallet(payer), row.total_minor], BANK)
        send(token_label(row.currency), "approve", [escrow_addr, row.total_minor], payer)
        created = send(
            ESCROW,
            "create",
            [
                token_addr,
                chain.wallet(recipient_wallet(row.recipient_id)),
                _hash32(f"{row.id}|{row.reference}"),
                [t["amount_minor"] for t in row.plan_json],
                [release_timestamp(date.fromisoformat(t["release_on"])) for t in row.plan_json],
            ],
            payer,
        )
        event = next(e for e in created.events if e["event"] == "Created")
        now = self._clock.now()
        row.chain_escrow_id = int(event["args"]["id"])
        row.status = EscrowStatus.ON_CHAIN.value
        row.confirmed_at = now
        row.updated_at = now
        proof.used_at = now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.funded",
            payment_id=row.id,
            amount_minor=row.total_minor,
            currency=row.currency,
            recipient_id=row.recipient_id,
            decision=Decision.APPROVED,
            reason_code=auth.proof_reference(proof),
            detail=(
                f"{len(row.plan_json)} tranche(s) locked on the sandbox chain, "
                f"escrow #{row.chain_escrow_id}, tx {created.tx_hash[:12]}"
            ),
            input_hash=row.plan_hash,
            output_hash=created.tx_hash,
        )
        return row

    def release_early(
        self, session: Session, actor: Actor, escrow_id: str, index: int, mfa_raw: str | None
    ) -> Escrow:
        """The parent pays one tranche before its date. A human decision, so it needs MFA."""
        authorize(actor, Perm.ESCROW_WRITE)
        row = self._load(session, actor, escrow_id)
        chain_id = self._on_chain(row)
        proof = self._proof(session, actor, MFA_RELEASE, row, mfa_raw)
        amount = self._tranche_amount(row, index)
        tx = self._chain.send(
            session, contract=ESCROW, function="releaseEarly", args=[chain_id, index],
            caller=user_wallet(row.owner_id), actor_id=actor.user_id, ref=row.id,
        )  # fmt: skip
        now = self._clock.now()
        proof.used_at = now
        row.updated_at = now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.tranche_released",
            payment_id=row.id,
            amount_minor=amount,
            currency=row.currency,
            recipient_id=row.recipient_id,
            decision=Decision.APPROVED,
            reason_code=auth.proof_reference(proof),
            detail=f"Tranche {index + 1} paid early by the parent, tx {tx.tx_hash[:12]}",
            output_hash=tx.tx_hash,
        )
        return row

    def cancel(self, session: Session, actor: Actor, escrow_id: str, mfa_raw: str | None) -> Escrow:
        """The parent takes back every tranche that is not yet due. Needs MFA."""
        authorize(actor, Perm.ESCROW_WRITE)
        row = self._load(session, actor, escrow_id)
        chain_id = self._on_chain(row)
        proof = self._proof(session, actor, MFA_CANCEL, row, mfa_raw)
        tx = self._chain.send(
            session, contract=ESCROW, function="cancel", args=[chain_id],
            caller=user_wallet(row.owner_id), actor_id=actor.user_id, ref=row.id,
        )  # fmt: skip
        refunded = next(e for e in tx.events if e["event"] == "Cancelled")["args"]["refunded"]
        now = self._clock.now()
        proof.used_at = now
        row.updated_at = now
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.cancelled",
            payment_id=row.id,
            amount_minor=int(refunded),
            currency=row.currency,
            recipient_id=row.recipient_id,
            decision=Decision.APPROVED,
            reason_code=auth.proof_reference(proof),
            detail=f"Tranches not yet due taken back by the parent, tx {tx.tx_hash[:12]}",
            output_hash=tx.tx_hash,
        )
        return row

    # --- compliance and sandbox control ---------------------------------------------------------
    def freeze(self, session: Session, actor: Actor, escrow_id: str, reason: str) -> Escrow:
        """The bank's compliance reviewer stops all movement. The funds stay where they are."""
        authorize(actor, Perm.ESCROW_FREEZE)
        reason = self._reason(reason)
        row = self._load(session, actor, escrow_id)
        tx = self._chain.send(
            session, contract=ESCROW, function="freeze",
            args=[self._on_chain(row), _hash32(reason)], caller=COMPLIANCE,
            actor_id=actor.user_id, ref=row.id,
        )  # fmt: skip
        row.updated_at = self._clock.now()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.frozen",
            payment_id=row.id,
            amount_minor=row.total_minor,
            currency=row.currency,
            decision=Decision.BLOCKED,
            reason_code="COMPLIANCE_HOLD",
            detail=f"Frozen by a reviewer: {reason}",
            output_hash=tx.tx_hash,
        )
        return row

    def unfreeze(self, session: Session, actor: Actor, escrow_id: str, reason: str) -> Escrow:
        authorize(actor, Perm.ESCROW_FREEZE)
        reason = self._reason(reason)
        row = self._load(session, actor, escrow_id)
        tx = self._chain.send(
            session, contract=ESCROW, function="unfreeze", args=[self._on_chain(row)],
            caller=COMPLIANCE, actor_id=actor.user_id, ref=row.id,
        )  # fmt: skip
        row.updated_at = self._clock.now()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.unfrozen",
            payment_id=row.id,
            amount_minor=row.total_minor,
            currency=row.currency,
            decision=Decision.APPROVED,
            reason_code="COMPLIANCE_RELEASE",
            detail=f"Unfrozen by a reviewer: {reason}",
            output_hash=tx.tx_hash,
        )
        return row

    def university_refund(
        self, session: Session, actor: Actor, escrow_id: str, index: int
    ) -> Escrow:
        """Sandbox control: the university sends a tranche back (a refused visa, for example)."""
        authorize(actor, Perm.SANDBOX_CONTROL)
        row = self._load(session, actor, escrow_id)
        amount = self._tranche_amount(row, index)
        tx = self._chain.send(
            session, contract=ESCROW, function="refund", args=[self._on_chain(row), index],
            caller=recipient_wallet(row.recipient_id), actor_id=actor.user_id, ref=row.id,
        )  # fmt: skip
        row.updated_at = self._clock.now()
        self._audit.append(
            session,
            actor_type=actor.audit_type,
            actor_id=actor.user_id,
            action="escrow.tranche_returned",
            payment_id=row.id,
            amount_minor=amount,
            currency=row.currency,
            recipient_id=row.recipient_id,
            decision=Decision.APPROVED,
            reason_code="BENEFICIARY_REFUND",
            detail=(
                f"Tranche {index + 1} returned by the university (simulated), tx {tx.tx_hash[:12]}"
            ),
            output_hash=tx.tx_hash,
        )
        return row

    # --- the schedule runs itself ---------------------------------------------------------------
    def release_due(self, session: Session, escrow_id: str) -> int:
        """Pay every tranche whose date has come. The university claims it, as a standing order."""
        row = session.get(Escrow, escrow_id)
        if row is None or row.status != EscrowStatus.ON_CHAIN.value:
            return 0
        chain_id = self._on_chain(row)
        released = 0
        for tranche in self._chain_tranches(session, row, chain_id):
            if tranche["state"] != "LOCKED" or not tranche["due"]:
                continue
            if self._chain_status(session, chain_id) != "ACTIVE":
                break
            tx = self._chain.send(
                session, contract=ESCROW, function="releaseDue", args=[chain_id, tranche["index"]],
                caller=recipient_wallet(row.recipient_id), actor_id="system", ref=row.id,
            )  # fmt: skip
            row.updated_at = self._clock.now()
            self._audit.append(
                session,
                actor_type=ActorType.SYSTEM,
                actor_id="system",
                action="escrow.tranche_released",
                payment_id=row.id,
                amount_minor=tranche["amount_minor"],
                currency=row.currency,
                recipient_id=row.recipient_id,
                decision=Decision.APPROVED,
                reason_code="SCHEDULED",
                detail=f"Tranche {tranche['index'] + 1} paid on its date, tx {tx.tx_hash[:12]}",
                output_hash=tx.tx_hash,
            )
            released += 1
        return released

    def due_escrow_ids(self, session: Session) -> list[str]:
        """Live escrows that may have a tranche to pay. Cheap: the plan holds the dates."""
        now_day = datetime.fromtimestamp(self._chain.chain_time(session), tz=UTC).date().isoformat()
        rows = session.execute(
            select(Escrow).where(Escrow.status == EscrowStatus.ON_CHAIN.value)
        ).scalars()
        return [r.id for r in rows if any(t["release_on"] <= now_day for t in r.plan_json)]

    def advance_due(self, db: Any) -> int:
        """One worker tick: pay due tranches. Each escrow is its own short transaction."""
        with db.read() as session:
            ids = self.due_escrow_ids(session)
        paid = 0
        for escrow_id in ids:
            try:
                with db.write() as session:
                    paid += self.release_due(session, escrow_id)
            except errors.ApiError:
                continue  # a frozen or finished escrow is simply skipped
        return paid

    # --- reading ----------------------------------------------------------------------------------
    def list(self, session: Session, actor: Actor) -> list[Escrow]:
        authorize(actor, Perm.ESCROW_READ)
        stmt = select(Escrow).order_by(Escrow.created_at.desc())
        if actor.owner_id is not None:
            stmt = stmt.where(Escrow.owner_id == actor.owner_id)
        return list(session.execute(stmt).scalars())

    def get(self, session: Session, actor: Actor, escrow_id: str) -> Escrow:
        authorize(actor, Perm.ESCROW_READ)
        return self._load(session, actor, escrow_id)

    def view(
        self, session: Session, actor: Actor, row: Escrow, *, detail: bool = False
    ) -> dict[str, Any]:
        recipient = session.get(Recipient, row.recipient_id)
        chain_status: str | None = None
        tranches = [
            {
                "index": t["index"],
                "amount": Money(t["amount_minor"], row.currency).to_dict(),
                "release_on": t["release_on"],
                "state": "PLANNED",
                "due": False,
            }
            for t in row.plan_json
        ]
        chain_info: dict[str, Any] | None = None
        if row.status == EscrowStatus.ON_CHAIN.value and row.chain_escrow_id is not None:
            chain_id = int(row.chain_escrow_id)
            chain_status = self._chain_status(session, chain_id)
            tranches = [
                {
                    "index": t["index"],
                    "amount": Money(t["amount_minor"], row.currency).to_dict(),
                    "release_on": t["release_on"],
                    "state": t["state"],
                    "due": t["due"],
                }
                for t in self._chain_tranches(session, row, chain_id)
            ]
            locked = int(self._chain.call(session, ESCROW, "getEscrow", [chain_id])[5])
            chain_info = {
                "escrow_id": chain_id,
                "contract": self._chain.address(session, ESCROW),
                "token": self._chain.address(session, token_label(row.currency)),
                "payer_wallet": self._chain.wallet(user_wallet(row.owner_id)),
                "beneficiary_wallet": self._chain.wallet(recipient_wallet(row.recipient_id)),
                "locked": Money(locked, row.currency).to_dict(),
                "chain_time": iso_utc_from_epoch(self._chain.chain_time(session)),
            }
        view: dict[str, Any] = {
            "escrow_id": row.id,
            "status": row.status,
            "chain_status": chain_status,
            "purpose": row.purpose,
            "cadence": row.cadence,
            "currency": row.currency,
            "total": Money(row.total_minor, row.currency).to_dict(),
            "reference": row.reference,
            "recipient": {
                "recipient_id": row.recipient_id,
                "label": self._recipients.label(recipient) if recipient else "",
            },
            "tranches": tranches,
            "plan_hash": row.plan_hash,
            "created_at": iso_utc(row.created_at),
            "confirmed_at": iso_utc(row.confirmed_at) if row.confirmed_at else None,
            "chain": chain_info,
            "simulated": True,
        }
        if detail:
            view["transactions"] = self._chain.transactions(session, row.id)
            owner = session.get(User, row.owner_id)
            view["blockers"] = self._blockers(row, owner)
        return view

    # --- internals --------------------------------------------------------------------------------
    @staticmethod
    def _blockers(row: Escrow, owner: User | None) -> list[dict[str, str]]:
        if row.status != EscrowStatus.PENDING_CONFIRMATION.value:
            return []
        if owner is None or owner.kyc_status != "VERIFIED":
            return [
                {
                    "code": "KYC_NOT_VERIFIED",
                    "message": "KYC must be verified before funds can be locked (simulated).",
                }
            ]
        return []

    @staticmethod
    def _reason(reason: str) -> str:
        cleaned = " ".join(reason.split())
        if not 3 <= len(cleaned) <= MAX_REASON:
            raise errors.ValidationFailed(f"Give a reason of 3 to {MAX_REASON} characters.")
        return cleaned

    @staticmethod
    def _tranche_amount(row: Escrow, index: int) -> int:
        if not 0 <= index < len(row.plan_json):
            raise errors.NotFound("That tranche does not exist.")
        return int(row.plan_json[index]["amount_minor"])

    def _chain_status(self, session: Session, chain_id: int) -> str:
        return CHAIN_STATUS[int(self._chain.call(session, ESCROW, "getEscrow", [chain_id])[4])]

    def _chain_tranches(self, session: Session, row: Escrow, chain_id: int) -> list[dict[str, Any]]:
        now = self._chain.chain_time(session)
        found = []
        for plan in row.plan_json:
            amount, release_after, state = self._chain.call(
                session, ESCROW, "getTranche", [chain_id, plan["index"]]
            )
            name = TRANCHE_STATE[int(state)]
            found.append(
                {
                    "index": plan["index"],
                    "amount_minor": int(amount),
                    "release_on": plan["release_on"],
                    "state": name,
                    "due": name == "LOCKED" and now >= int(release_after),
                }
            )
        return found
