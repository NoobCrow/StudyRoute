"""The sandbox chain as a service.

The EVM lives in memory, so the chain's history is kept in the database as an append-only,
hash-chained log (table chain_log). Replaying the log rebuilds the chain exactly: the same
addresses, balances and block numbers. That gives three things:

  * the chain survives a restart, and several workers can share one history;
  * a transaction only counts once its row is committed with the rest of the request, so a
    request that fails halfway leaves no trace on the chain (the chain is rebuilt from the log);
  * editing the log behind the application's back is detected, because every row's hash covers
    the row before it.

Nothing here is a real network and no key exists. The server acts as each party only after the
domain layer has authorised the human behind that party (with MFA where money moves).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.chain import GENESIS
from app.audit.service import AuditService
from app.chain.artifacts import load
from app.chain.evm import ChainRevert, Receipt, SandboxChain, wallet_address
from app.core import errors
from app.core.clock import Clock, iso_utc
from app.core.crypto import canonical_json, sha256_hex
from app.domain.constants import ActorType
from app.models import AuditEvent, ChainLog

BANK = "bank"
COMPLIANCE = "compliance"
ESCROW = "escrow"
ANCHOR = "anchor"

REVERT_TEXT = {
    "NOT_DUE": "This tranche is not due yet.",
    "NOT_ACTIVE": "This escrow is frozen or already finished, so nothing can move.",
    "NOT_FROZEN": "This escrow is not frozen.",
    "NOT_LOCKED": "This tranche was already paid or returned.",
    "NOTHING_TO_CANCEL": "Nothing can be cancelled: every remaining tranche is already due.",
    "NO_SUCH_ESCROW": "That escrow does not exist on the chain.",
    "NO_SUCH_TRANCHE": "That tranche does not exist.",
    "INSUFFICIENT_BALANCE": "The wallet does not hold enough tokenised deposit.",
    "INSUFFICIENT_ALLOWANCE": "The escrow was not allowed to take that much.",
    "SEQ_NOT_INCREASING": "That audit position is already anchored.",
}
NOT_YOURS = {
    "ONLY_PAYER",
    "ONLY_BENEFICIARY",
    "NOT_A_PARTY",
    "ONLY_COMPLIANCE",
    "ONLY_OPERATOR",
    "ONLY_ISSUER",
}


def token_label(currency: str) -> str:
    return f"token:{currency}"


def user_wallet(user_id: str) -> str:
    return f"user:{user_id}"


def recipient_wallet(recipient_id: str) -> str:
    return f"recipient:{recipient_id}"


def refusal(reason: str) -> errors.ApiError:
    """Turn a contract revert into the API's own error."""
    if reason in NOT_YOURS:
        text = "The contract refused: that action belongs to a different party."
    else:
        text = REVERT_TEXT.get(reason, f"The contract refused the transaction ({reason}).")
    return errors.InvalidState(text, extra={"chain_reason": reason})


@dataclass(frozen=True)
class TxRecord:
    seq: int
    tx_hash: str
    block: int
    timestamp: int
    contract: str
    function: str
    caller: str
    events: tuple[dict[str, Any], ...]
    output: tuple[Any, ...]
    gas_used: int

    def to_api(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tx_hash": self.tx_hash,
            "block": self.block,
            "time": iso_utc_from_epoch(self.timestamp),
            "contract": self.contract,
            "function": self.function,
            "sender": self.caller,
            "events": list(self.events),
        }


def iso_utc_from_epoch(seconds: int) -> str:
    from datetime import UTC, datetime

    return iso_utc(datetime.fromtimestamp(seconds, tz=UTC))


def _entry(row: ChainLog) -> dict[str, Any]:
    return {
        "seq": row.seq,
        "kind": row.kind,
        "contract": row.contract,
        "function": row.function,
        "caller": row.caller,
        "args": row.args_json,
        "at": row.at,
        "ref": row.ref,
        "actor_id": row.actor_id,
    }


def _tx_hash(prev: str, entry: dict[str, Any]) -> str:
    return sha256_hex(prev.encode("utf-8") + canonical_json(entry))


class ChainService:
    def __init__(self, clock: Clock, audit: AuditService) -> None:
        self._clock = clock
        self._audit = audit
        self._lock = threading.RLock()
        self._chain: SandboxChain | None = None
        self._applied = 0
        self._head = GENESIS
        self._offset = 0  # seconds the sandbox has moved chain time ahead of the real clock
        self._dirty = False
        self._broken: str | None = None

    # --- keeping the in-memory chain equal to the log ------------------------------------------
    def _fresh(self) -> SandboxChain:
        self._chain = SandboxChain()
        self._applied = 0
        self._head = GENESIS
        self._offset = 0
        self._dirty = False
        self._broken = None
        return self._chain

    def ensure_synced(self, session: Session) -> SandboxChain:
        with self._lock:
            if self._chain is None or self._dirty:
                return self._rebuild(session)
            last = session.scalar(select(func.max(ChainLog.seq))) or 0
            if last < self._applied:
                return self._rebuild(session)  # transactions of a request that did not commit
            if last == self._applied:
                row = session.get(ChainLog, last) if last else None
                if (row.tx_hash if row else GENESIS) != self._head:
                    return self._rebuild(session)
                return self._chain
            rows = session.execute(
                select(ChainLog).where(ChainLog.seq > self._applied).order_by(ChainLog.seq)
            ).scalars().all()  # fmt: skip
            if rows[0].prev_hash != self._head:
                return self._rebuild(session)
            for row in rows:
                if not self._apply(row):
                    break
            return self._chain

    def _rebuild(self, session: Session) -> SandboxChain:
        chain = self._fresh()
        rows = session.execute(select(ChainLog).order_by(ChainLog.seq)).scalars().all()
        for row in rows:
            if not self._apply(row):
                break
        return chain

    def _apply(self, row: ChainLog) -> bool:
        """Check one logged row against the hash chain, then run it. False stops the replay."""
        chain = self._chain
        if chain is None:
            raise RuntimeError("the sandbox chain has not been started")
        entry = _entry(row)
        if row.seq != self._applied + 1 or row.prev_hash != self._head:
            self._broken = f"The chain log has a gap or a broken link at row {row.seq}."
            return False
        if _tx_hash(row.prev_hash, entry) != row.tx_hash:
            self._broken = f"Row {row.seq} of the chain log was changed after it was written."
            return False
        try:
            if row.kind == "DEPLOY":
                chain.deploy(row.contract, str(row.function), row.args_json, row.caller, row.at)
            elif row.kind == "CALL":
                chain.send(row.contract, str(row.function), row.args_json, row.caller, row.at)
            elif row.kind == "TIME":
                chain.advance(row.at)
                self._offset += int(row.args_json[0])
            else:
                raise ValueError(f"unknown kind {row.kind}")
        except Exception as exc:  # a logged row that no longer replays means the log is not trusted
            self._broken = f"Row {row.seq} of the chain log no longer replays ({exc})."
            return False
        self._applied = row.seq
        self._head = row.tx_hash
        return True

    def _append(
        self,
        session: Session,
        *,
        kind: str,
        contract: str,
        function: str | None,
        caller: str,
        args: list[Any],
        at: int,
        ref: str | None,
        actor_id: str,
    ) -> ChainLog:
        row = ChainLog(
            seq=self._applied + 1,
            kind=kind,
            contract=contract,
            function=function,
            caller=caller,
            args_json=args,
            at=at,
            ref=ref,
            actor_id=actor_id,
            prev_hash=self._head,
            tx_hash="",
            created_at=self._clock.now(),
        )
        row.tx_hash = _tx_hash(self._head, _entry(row))
        session.add(row)
        session.flush()
        self._applied = row.seq
        self._head = row.tx_hash
        return row

    def _now(self) -> int:
        return int(self._clock.now().timestamp()) + self._offset

    def _writable(self, session: Session) -> SandboxChain:
        chain = self.ensure_synced(session)
        if self._broken:
            raise errors.InvalidState(
                "The chain log failed its integrity check, so the sandbox chain is stopped.",
                extra={"chain_reason": "LOG_CORRUPT"},
            )
        return chain

    # --- writing (always inside the caller's write transaction) ---------------------------------
    def deploy(
        self, session: Session, *, label: str, contract: str, args: list[Any], caller: str,
        actor_id: str, ref: str | None = None,
    ) -> str:  # fmt: skip
        with self._lock:
            chain = self._writable(session)
            deployed = chain.deploy(label, contract, args, caller, self._now())
            try:
                self._append(
                    session, kind="DEPLOY", contract=label, function=contract, caller=caller,
                    args=args, at=chain.timestamp, ref=ref, actor_id=actor_id,
                )  # fmt: skip
            except BaseException:
                self._dirty = True
                raise
            return deployed.address

    def send(
        self, session: Session, *, contract: str, function: str, args: list[Any], caller: str,
        actor_id: str, ref: str | None = None,
    ) -> TxRecord:  # fmt: skip
        with self._lock:
            chain = self._writable(session)
            try:
                receipt = chain.send(contract, function, args, caller, self._now())
            except ChainRevert as exc:
                raise refusal(exc.reason) from exc
            try:
                row = self._append(
                    session, kind="CALL", contract=contract, function=function, caller=caller,
                    args=args, at=receipt.timestamp, ref=ref, actor_id=actor_id,
                )  # fmt: skip
            except BaseException:
                self._dirty = True
                raise
            return self._record(row, receipt)

    def advance(self, session: Session, *, seconds: int, actor_id: str) -> int:
        """A sandbox control: move chain time forward, as if days had passed. Returns chain time."""
        if not 0 < seconds <= 366 * 86_400:
            raise errors.ValidationFailed("Advance by 1 second up to 366 days.")
        with self._lock:
            chain = self._writable(session)
            target = max(self._now(), chain.timestamp) + seconds
            chain.advance(target)
            try:
                self._append(
                    session, kind="TIME", contract="clock", function=None, caller=BANK,
                    args=[seconds], at=target, ref=None, actor_id=actor_id,
                )  # fmt: skip
            except BaseException:
                self._dirty = True
                raise
            self._offset += seconds
            return target

    def bootstrap(self, session: Session) -> bool:
        """Deploy the escrow and the audit anchor if this database has never had them.

        Returns True if it deployed. The caller writes the audit event."""
        with self._lock:
            chain = self._writable(session)
            deployed = False
            if not chain.has(ESCROW):
                self.deploy(
                    session, label=ESCROW, contract="TuitionEscrow",
                    args=[wallet_address(COMPLIANCE)], caller=BANK, actor_id="system",
                )  # fmt: skip
                deployed = True
            if not chain.has(ANCHOR):
                self.deploy(
                    session, label=ANCHOR, contract="AuditAnchor",
                    args=[wallet_address(BANK)], caller=BANK, actor_id="system",
                )  # fmt: skip
                deployed = True
            return deployed

    def ensure_token(self, session: Session, currency: str, exponent: int, actor_id: str) -> str:
        """The bank's tokenised deposit for one currency, deployed the first time it is needed."""
        label = token_label(currency)
        with self._lock:
            chain = self._writable(session)
            if not chain.has(label):
                self.deploy(
                    session, label=label, contract="TokenisedDeposit",
                    args=[f"Tokenised deposit {currency} (sandbox)", f"t{currency}", exponent,
                          wallet_address(BANK)],
                    caller=BANK, actor_id=actor_id,
                )  # fmt: skip
            return chain.deployed(label).address

    def ready(self, session: Session) -> None:
        """Deploy on first use and write the one audit event that says so."""
        if self.bootstrap(session):
            self._audit.append(
                session,
                actor_type=ActorType.SYSTEM,
                actor_id="system",
                action="system.chain_ready",
                detail="Sandbox chain started: escrow and audit-anchor contracts deployed",
            )

    # --- reading -----------------------------------------------------------------------------
    def call(
        self, session: Session, contract: str, function: str, args: list[Any]
    ) -> tuple[Any, ...]:
        with self._lock:
            chain = self.ensure_synced(session)
            try:
                return chain.call(contract, function, args)
            except ChainRevert as exc:
                raise refusal(exc.reason) from exc

    def wallet(self, label: str) -> str:
        return wallet_address(label)

    def address(self, session: Session, label: str) -> str:
        with self._lock:
            return self.ensure_synced(session).deployed(label).address

    def chain_time(self, session: Session) -> int:
        with self._lock:
            chain = self.ensure_synced(session)
            return max(self._now(), chain.timestamp)

    def transactions(self, session: Session, ref: str, limit: int = 200) -> list[dict[str, Any]]:
        """The logged transactions that belong to one escrow (or other reference)."""
        rows = session.execute(
            select(ChainLog).where(ChainLog.ref == ref).order_by(ChainLog.seq).limit(limit)
        ).scalars().all()  # fmt: skip
        return [
            {
                "seq": r.seq,
                "tx_hash": r.tx_hash,
                "kind": r.kind,
                "contract": r.contract,
                "function": r.function,
                "sender": r.caller,
                "time": iso_utc_from_epoch(r.at),
            }
            for r in rows
        ]

    def status(self, session: Session) -> dict[str, Any]:
        with self._lock:
            chain = self.ensure_synced(session)
            contracts = []
            for label in chain.labels():
                deployed = chain.deployed(label)
                artifact = load(deployed.artifact.name)
                contracts.append(
                    {
                        "label": label,
                        "contract": artifact.name,
                        "address": deployed.address,
                        "source_file": artifact.source_file,
                        "source_sha256": artifact.source_sha256,
                        "solc": artifact.solc,
                    }
                )
            return {
                "simulated": True,
                "engine": "py-evm, an in-memory EVM. No network, no peers, no real tokens.",
                "ready": chain.has(ESCROW) and chain.has(ANCHOR),
                "block": chain.block,
                "chain_time": iso_utc_from_epoch(max(self._now(), chain.timestamp)),
                "time_offset_seconds": self._offset,
                "contracts": contracts,
                "log": {"transactions": self._applied, "head": self._head},
                "integrity": {"ok": self._broken is None, "problem": self._broken},
            }

    # --- anchoring the audit log -----------------------------------------------------------------
    def anchor_audit(self, session: Session, actor_id: str) -> dict[str, Any]:
        """Write the audit log's newest hash onto the chain, outside the database."""
        self.ready(session)
        head = self._audit.ensure_head(session)
        if head.seq == 0:
            raise errors.InvalidState("The audit log is empty: there is nothing to anchor yet.")
        seq, digest = int(head.seq), str(head.hash)
        tx = self.send(
            session, contract=ANCHOR, function="anchor", args=[seq, "0x" + digest], caller=BANK,
            actor_id=actor_id, ref=f"audit:{seq}",
        )  # fmt: skip
        self._audit.append(
            session,
            actor_type=ActorType.USER,
            actor_id=actor_id,
            action="chain.anchored",
            detail=f"Audit head {seq} anchored on the sandbox chain (tx {tx.tx_hash[:12]})",
            input_hash=digest,
        )
        return {"seq": seq, "head": digest, "tx": tx.to_api()}

    def anchors(self, session: Session) -> list[dict[str, Any]]:
        with self._lock:
            chain = self.ensure_synced(session)
            if not chain.has(ANCHOR):
                return []
            count = int(chain.call(ANCHOR, "count", [])[0])
            found = []
            for index in range(count):
                seq, at, head = chain.call(ANCHOR, "get", [index])
                found.append(
                    {"index": index, "seq": int(seq), "head": str(head).removeprefix("0x"),
                     "time": iso_utc_from_epoch(int(at))}
                )  # fmt: skip
            return found

    def verify_anchors(self, session: Session) -> dict[str, Any]:
        """Compare every anchored hash with the database. An attacker who rewrites the audit
        log AND recomputes its hashes still cannot change what is written on the chain."""
        verdict = self._audit.verify(session)
        results = []
        for anchor in self.anchors(session):
            event = session.execute(
                select(AuditEvent).where(AuditEvent.seq == anchor["seq"])
            ).scalar_one_or_none()
            if event is None:
                state = "MISSING_EVENT"
            elif event.this_event_hash == anchor["head"]:
                state = "MATCH"
            else:
                state = "MISMATCH"
            results.append(
                {
                    **anchor,
                    "database_hash": event.this_event_hash if event else None,
                    "state": state,
                }
            )
        failed = [r for r in results if r["state"] != "MATCH"]
        intact = verdict.ok and not failed
        status = "PASS" if intact else "FAIL"
        if not results:
            status = "NO_ANCHOR"
        return {
            "status": status,
            "audit_chain": verdict.to_api_dict(),
            "anchors": results,
            "failed": [r["index"] for r in failed],
            "simulated": True,
        }

    # --- helpers ---
    @staticmethod
    def _record(row: ChainLog, receipt: Receipt) -> TxRecord:
        events = tuple(
            {"contract": e.contract, "event": e.name, "args": e.args} for e in receipt.events
        )
        return TxRecord(
            seq=row.seq, tx_hash=row.tx_hash, block=receipt.block, timestamp=receipt.timestamp,
            contract=row.contract, function=str(row.function), caller=row.caller, events=events,
            output=receipt.output, gas_used=receipt.gas_used,
        )  # fmt: skip
