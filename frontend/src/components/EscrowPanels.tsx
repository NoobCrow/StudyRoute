import { useState } from "react";
import type { FormEvent } from "react";

import { get, post } from "../api/client";
import type {
  AnchorVerdict, ChainAnchor, ChainEscrowStatus, ChainStatus, EscrowTranche, EscrowView, TrancheState,
} from "../api/types";
import { useIdempotencyKey } from "../idempotency";
import { formatDateTime } from "../lib/format";
import { MfaDialog } from "./MfaDialog";
import { Badge, ErrorNotice, Field, Notice } from "./Ui";

type Tone = "ok" | "warn" | "danger" | "info" | "neutral";

const CHAIN_LABEL: Record<ChainEscrowStatus, { tone: Tone; text: string }> = {
  ACTIVE: { tone: "ok", text: "Active on the chain" },
  FROZEN: { tone: "danger", text: "Frozen by the bank's reviewer" },
  COMPLETED: { tone: "ok", text: "Completed" },
  CANCELLED: { tone: "neutral", text: "Cancelled" },
};

function statusBadge(escrow: EscrowView) {
  if (escrow.chain_status) {
    const label = CHAIN_LABEL[escrow.chain_status];
    return <Badge tone={label.tone}>{label.text}</Badge>;
  }
  if (escrow.status === "ABANDONED") return <Badge tone="neutral">Plan dropped</Badge>;
  return <Badge tone="warn">Waiting for MFA confirmation</Badge>;
}

const TRANCHE_LABEL: Record<TrancheState, { tone: Tone; text: string }> = {
  PLANNED: { tone: "neutral", text: "Planned" },
  LOCKED: { tone: "info", text: "Locked" },
  RELEASED: { tone: "ok", text: "Paid" },
  REFUNDED: { tone: "warn", text: "Returned to the parent" },
};

export function shortHash(hash: string, keep = 10): string {
  return hash.length <= keep * 2 + 1 ? hash : `${hash.slice(0, keep)}...${hash.slice(-4)}`;
}

interface TrancheRowProps {
  tranche: EscrowTranche;
  canPay: boolean;
  canControl: boolean;
  frozen: boolean;
  busy: boolean;
  onPay: (index: number) => void;
  onReturn: (index: number) => void;
}

function TrancheRow({ tranche, canPay, canControl, frozen, busy, onPay, onReturn }: TrancheRowProps) {
  const label = TRANCHE_LABEL[tranche.state];
  const locked = tranche.state === "LOCKED";
  return (
    <tr>
      <td>{tranche.index + 1}</td>
      <td className="nowrap">{tranche.release_on}</td>
      <td className="num">{tranche.amount.formatted}</td>
      <td>
        <Badge tone={label.tone}>{label.text}</Badge>
        {locked && tranche.due ? <> <Badge tone="info">Due now</Badge></> : null}
      </td>
      <td>
        <div className="row">
          {locked && canPay ? (
            <button
              type="button" className="btn small" disabled={busy || frozen}
              onClick={() => onPay(tranche.index)}
              aria-label={`Pay tranche ${tranche.index + 1} now`}
            >
              Pay now
            </button>
          ) : null}
          {locked && canControl ? (
            <button
              type="button" className="btn small ghost" disabled={busy || frozen}
              onClick={() => onReturn(tranche.index)}
              aria-label={`University returns tranche ${tranche.index + 1} (simulated)`}
            >
              University returns it
            </button>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

function ProofPanel({ escrow }: { escrow: EscrowView }) {
  const chain = escrow.chain;
  const tag = escrow.escrow_id.slice(-6);
  if (!chain) return null;
  return (
    <details>
      <summary>On-chain proof ({escrow.transactions?.length ?? 0} transactions)</summary>
      <dl className="kv">
        <dt>Escrow number</dt><dd>#{chain.escrow_id} in the escrow contract</dd>
        <dt>Escrow contract</dt><dd className="mono mono-wrap">{chain.contract}</dd>
        <dt>Deposit token</dt><dd className="mono mono-wrap">{chain.token}</dd>
        <dt>Parent&apos;s wallet</dt><dd className="mono mono-wrap">{chain.payer_wallet}</dd>
        <dt>University&apos;s wallet</dt><dd className="mono mono-wrap">{chain.beneficiary_wallet}</dd>
        <dt>Plan hash</dt><dd className="mono mono-wrap">{escrow.plan_hash}</dd>
        <dt>Still locked</dt><dd>{chain.locked.formatted}</dd>
      </dl>
      <p className="small muted">
        Only amounts, dates and hashes are on the chain. The payment reference is stored as a hash;
        no name, account number or BIC ever is.
      </p>
      {escrow.transactions && escrow.transactions.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label={`Chain transactions of ${tag}`}>
          <table>
            <caption className="sr-only">Transactions on the simulated chain for this escrow</caption>
            <thead>
              <tr>
                <th scope="col" className="num">#</th>
                <th scope="col">Call</th>
                <th scope="col">Sent by</th>
                <th scope="col">Transaction id</th>
                <th scope="col" className="hide-narrow">Time</th>
              </tr>
            </thead>
            <tbody>
              {escrow.transactions.map((tx) => (
                <tr key={tx.seq}>
                  <td className="num">{tx.seq}</td>
                  <td><code>{tx.contract}.{tx.function}</code></td>
                  <td>{tx.sender.split(":")[0]}</td>
                  <td><code title={tx.tx_hash}>{shortHash(tx.tx_hash)}</code></td>
                  <td className="hide-narrow nowrap">{formatDateTime(tx.time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </details>
  );
}

type Asking = { scope: "confirm_escrow" } | { scope: "release_escrow"; index: number } | { scope: "cancel_escrow" };

interface EscrowCardProps {
  escrow: EscrowView;
  canWrite: boolean;
  canFreeze: boolean;
  canControl: boolean;
  sandboxCode?: string;
  onChanged: () => void;
}

/** One escrow: its schedule, the human steps (MFA), the reviewer's freeze, and the proof on the chain. */
export function EscrowCard({ escrow, canWrite, canFreeze, canControl, sandboxCode, onChanged }: EscrowCardProps) {
  const [asking, setAsking] = useState<Asking | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [reason, setReason] = useState("");
  const confirmKey = useIdempotencyKey(`confirm|${escrow.escrow_id}`);
  const cancelKey = useIdempotencyKey(`cancel|${escrow.escrow_id}|${escrow.tranches.map((t) => t.state).join()}`);
  const dropKey = useIdempotencyKey(`drop|${escrow.escrow_id}`);
  const [releaseIndex, setReleaseIndex] = useState(0);
  const releaseKey = useIdempotencyKey(`release|${escrow.escrow_id}|${releaseIndex}|${escrow.tranches.map((t) => t.state).join()}`);
  const id = escrow.escrow_id;
  const tag = id.slice(-6);
  const pending = escrow.status === "PENDING_CONFIRMATION";
  const live = escrow.chain_status === "ACTIVE";
  const frozen = escrow.chain_status === "FROZEN";
  const hasLocked = escrow.tranches.some((t) => t.state === "LOCKED");
  const blockers = escrow.blockers ?? [];

  async function run(work: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await work();
      onChanged();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  function withProof(proof: string) {
    const step = asking;
    setAsking(null);
    if (!step) return;
    if (step.scope === "confirm_escrow") {
      void run(() => post(`/escrows/${id}/confirm`, undefined, { idempotencyKey: confirmKey, mfaProof: proof }));
    } else if (step.scope === "release_escrow") {
      void run(() => post(`/escrows/${id}/tranches/${step.index}/release`, undefined, { idempotencyKey: releaseKey, mfaProof: proof }));
    } else {
      void run(() => post(`/escrows/${id}/cancel`, undefined, { idempotencyKey: cancelKey, mfaProof: proof }));
    }
  }

  function freezeOrThaw(event: FormEvent, action: "freeze" | "unfreeze") {
    event.preventDefault();
    void run(async () => {
      await post(`/escrows/${id}/${action}`, { reason: reason.trim() });
      setReason("");
    });
  }

  const dialogTitle =
    asking?.scope === "confirm_escrow" ? "Lock these funds in the escrow"
      : asking?.scope === "release_escrow" ? "Pay this tranche now"
        : "Cancel the tranches that are not yet due";

  return (
    <article className="card" aria-label={`Escrow ${escrow.reference} (${tag})`}>
      <div className="row between">
        <h3>{escrow.purpose === "TUITION" ? "Tuition" : "Living costs"}: {escrow.total.formatted}</h3>
        {statusBadge(escrow)}
      </div>
      <p className="muted">
        To {escrow.recipient.label || "the beneficiary"}. Reference <strong>{escrow.reference}</strong>.
        {" "}{escrow.tranches.length === 1 ? "One payment." : `${escrow.tranches.length} tranches, one a month.`}
      </p>
      <ErrorNotice error={error} />
      {frozen ? (
        <Notice tone="danger" title="Frozen">
          The bank&apos;s reviewer has stopped all movement. The funds stay locked in the contract.
          Nobody can pay, return or cancel until it is unfrozen.
        </Notice>
      ) : null}
      {pending && blockers.length > 0 ? (
        <Notice tone="warn" title="Not ready to lock funds">
          <ul>{blockers.map((b) => <li key={b.code}>{b.message}</li>)}</ul>
        </Notice>
      ) : null}
      <div className="table-wrap" tabIndex={0} role="region" aria-label={`Tranches of ${escrow.reference} (${tag})`}>
        <table>
          <caption className="sr-only">Release schedule</caption>
          <thead>
            <tr>
              <th scope="col">#</th>
              <th scope="col">Releases on</th>
              <th scope="col" className="num">Amount</th>
              <th scope="col">State</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {escrow.tranches.map((tranche) => (
              <TrancheRow
                key={tranche.index}
                tranche={tranche}
                canPay={canWrite && live}
                canControl={canControl && (live || frozen)}
                frozen={frozen}
                busy={busy}
                onPay={(index) => { setReleaseIndex(index); setAsking({ scope: "release_escrow", index }); }}
                onReturn={(index) => void run(() => post(`/escrows/${id}/tranches/${index}/sandbox-refund`))}
              />
            ))}
          </tbody>
        </table>
      </div>
      <div className="row">
        {pending && canWrite ? (
          <>
            <button type="button" className="btn primary" disabled={busy || blockers.length > 0} onClick={() => setAsking({ scope: "confirm_escrow" })}>
              Lock funds with MFA
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void run(() => post(`/escrows/${id}/abandon`, undefined, { idempotencyKey: dropKey }))}>
              Drop this plan
            </button>
          </>
        ) : null}
        {live && canWrite && hasLocked ? (
          <button type="button" className="btn danger" disabled={busy} onClick={() => setAsking({ scope: "cancel_escrow" })}>
            Cancel what is not yet due
          </button>
        ) : null}
      </div>
      {canFreeze && (live || frozen) ? (
        <form className="row" onSubmit={(e) => freezeOrThaw(e, frozen ? "unfreeze" : "freeze")} aria-label={`Reviewer control for ${tag}`}>
          <Field label={frozen ? "Reason to unfreeze" : "Reason to freeze"} htmlFor={`reason-${id}`}>
            <input id={`reason-${id}`} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={120} placeholder="Written in the audit log" />
          </Field>
          <button type="submit" className={frozen ? "btn" : "btn danger"} disabled={busy || reason.trim().length < 3}>
            {frozen ? "Unfreeze" : "Freeze this escrow"}
          </button>
        </form>
      ) : null}
      <ProofPanel escrow={escrow} />
      <p className="small muted">
        Simulated. The tokens are not money, no bank is contacted, and the chain is an in-memory sandbox.
      </p>
      {asking ? (
        <MfaDialog
          title={dialogTitle}
          scope={asking.scope}
          subjectId={id}
          sandboxCode={sandboxCode}
          onProof={withProof}
          onCancel={() => setAsking(null)}
        />
      ) : null}
    </article>
  );
}

/** The audit log's head hash, written on the chain where a database editor cannot reach it. */
export function AnchorCard({
  anchors, canAnchor, canVerify, onChanged,
}: { anchors: ChainAnchor[]; canAnchor: boolean; canVerify: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [verdict, setVerdict] = useState<AnchorVerdict | null>(null);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="anchor-title">
      <div className="row between">
        <h2 id="anchor-title">Audit anchor</h2>
        {verdict ? (
          <Badge tone={verdict.status === "PASS" ? "ok" : verdict.status === "FAIL" ? "danger" : "warn"}>
            {verdict.status === "PASS" ? "Database matches the chain" : verdict.status === "FAIL" ? "Does NOT match the chain" : "Nothing anchored yet"}
          </Badge>
        ) : null}
      </div>
      <p className="muted">
        The audit log is a SHA-256 hash chain, which catches an edited event unless the attacker also
        recomputes every hash after it. Writing the newest hash on the chain puts a copy where a
        database editor cannot reach, so that rewrite no longer goes unnoticed.
      </p>
      <ErrorNotice error={error} />
      {anchors.length === 0 ? <p className="muted">Nothing is anchored yet.</p> : (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Audit anchors table">
          <table>
            <caption className="sr-only">Audit log hashes written on the sandbox chain</caption>
            <thead>
              <tr><th scope="col" className="num">#</th><th scope="col" className="num">Audit event</th><th scope="col">Hash on the chain</th><th scope="col" className="hide-narrow">Anchored</th></tr>
            </thead>
            <tbody>
              {anchors.map((a) => (
                <tr key={a.index}>
                  <td className="num">{a.index + 1}</td>
                  <td className="num">{a.seq}</td>
                  <td><code title={a.head}>{shortHash(a.head)}</code></td>
                  <td className="hide-narrow nowrap">{formatDateTime(a.time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {verdict && verdict.anchors.length > 0 ? (
        <ul className="small">
          {verdict.anchors.map((a) => (
            <li key={a.index}>
              Anchor {a.index + 1} (audit event {a.seq}): <strong>{a.state === "MATCH" ? "matches" : a.state === "MISMATCH" ? "does not match" : "event is missing"}</strong>
            </li>
          ))}
          <li>
            Hash chain on its own: <strong>{verdict.audit_chain.status === "PASS" ? "passes" : `fails at event ${verdict.audit_chain.failed_seq ?? "?"}`}</strong>
          </li>
        </ul>
      ) : null}
      <div className="row">
        {canAnchor ? (
          <button type="button" className="btn primary" disabled={busy} onClick={() => void run(async () => { await post("/chain/anchor"); setVerdict(null); onChanged(); })}>
            Anchor the audit log now
          </button>
        ) : null}
        {canVerify ? (
          <button type="button" className="btn" disabled={busy} onClick={() => void run(async () => setVerdict(await get<AnchorVerdict>("/chain/verify")))}>
            Verify against the chain
          </button>
        ) : null}
      </div>
    </section>
  );
}

/** The contracts, where they are, and whether the replayable log is intact. */
export function ChainCard({ status }: { status: ChainStatus }) {
  return (
    <section className="card" aria-labelledby="chain-title">
      <div className="row between">
        <h2 id="chain-title">The simulated chain</h2>
        <Badge tone={status.integrity.ok ? "ok" : "danger"}>{status.integrity.ok ? "Log intact" : "Log failed its check"}</Badge>
      </div>
      <p className="muted">{status.engine} Solidity contracts, compiled and run for real; the money is not.</p>
      {status.integrity.problem ? <Notice tone="danger" title="Integrity problem">{status.integrity.problem}</Notice> : null}
      <dl className="kv">
        <dt>Blocks</dt><dd>{status.block}</dd>
        <dt>Chain time</dt>
        <dd>
          {formatDateTime(status.chain_time)}
          {status.time_offset_seconds > 0 ? ` (moved ${Math.round(status.time_offset_seconds / 86400)} days ahead by a reviewer)` : ""}
        </dd>
        <dt>Log head</dt><dd className="mono mono-wrap">{status.log.head}</dd>
      </dl>
      {status.contracts.length > 0 ? (
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Deployed contracts table">
          <table>
            <caption className="sr-only">Contracts deployed on the simulated chain</caption>
            <thead>
              <tr><th scope="col">Contract</th><th scope="col">Address</th><th scope="col" className="hide-narrow">Source SHA-256</th></tr>
            </thead>
            <tbody>
              {status.contracts.map((c) => (
                <tr key={c.label}>
                  <td><strong>{c.contract}</strong><div className="small muted">{c.label}</div></td>
                  <td><code title={c.address}>{shortHash(c.address, 12)}</code></td>
                  <td className="hide-narrow"><code title={c.source_sha256}>{shortHash(c.source_sha256, 8)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted">The contracts are deployed the first time an escrow is locked.</p>}
    </section>
  );
}

/** Sandbox control for the reviewer: let days pass so scheduled tranches can be seen paying out. */
export function TimeControl({ onChanged }: { onChanged: () => void }) {
  const [days, setDays] = useState("15");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [result, setResult] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const reply = await post<{ released: number }>("/chain/sandbox/advance", { days: Number(days) });
      setResult(`${reply.released} tranche${reply.released === 1 ? "" : "s"} paid.`);
      onChanged();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit} aria-labelledby="time-title">
      <h2 id="time-title">Sandbox clock</h2>
      <p className="muted">Let days pass on the chain, then the schedule pays whatever is due. Reviewer only.</p>
      <ErrorNotice error={error} />
      <div className="row">
        <Field label="Days to move forward" htmlFor="advance-days">
          <input id="advance-days" value={days} onChange={(e) => setDays(e.target.value)} inputMode="numeric" />
        </Field>
        <button type="submit" className="btn" disabled={busy || !/^[0-9]{1,3}$/.test(days) || Number(days) < 1}>Move time forward</button>
      </div>
      {result ? <p role="status">{result}</p> : null}
    </form>
  );
}
