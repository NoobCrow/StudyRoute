import { Fragment, useState } from "react";

import { post } from "../api/client";
import type { BankEvent, BankJournal, BankNetwork, BankStatus, BankTransfer, Money } from "../api/types";
import { useIdempotencyKey } from "../idempotency";
import { MfaDialog } from "./MfaDialog";
import { Badge, ErrorNotice, Notice } from "./Ui";

type Tone = "ok" | "warn" | "danger" | "info" | "neutral";

const STATUS_TONE: Record<BankStatus, Tone> = {
  PENDING_CONFIRMATION: "warn", ACCEPTED: "info", IN_TRANSIT: "info",
  SETTLED: "ok", RETURNED: "danger", CANCELLED: "neutral",
};
const STATUS_LABEL: Record<BankStatus, string> = {
  PENDING_CONFIRMATION: "Waiting for your confirmation", ACCEPTED: "Accepted", IN_TRANSIT: "In transit",
  SETTLED: "Settled", RETURNED: "Returned in full", CANCELLED: "Cancelled",
};

export function BankStatusBadge({ status }: { status: BankStatus }) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export const isOpen = (status: BankStatus) => status === "ACCEPTED" || status === "IN_TRANSIT";

function formatted(figures: Record<string, unknown>, key: string): string | null {
  const value = figures[key] as Partial<Money> | undefined;
  return value && typeof value.formatted === "string" ? value.formatted : null;
}

function Figures({ transfer }: { transfer: BankTransfer }) {
  const f = transfer.figures;
  const international = transfer.kind === "INTERNATIONAL";
  const rows: [string, string | null][] = international
    ? [
        ["You pay", formatted(f, "you_pay")],
        ["Beneficiary receives", formatted(f, "beneficiary_receives")],
        ["Charge code", String(f.charge_code ?? "")],
        ["Bank rate (BDT per unit)", String(f.provider_rate ?? "")],
        ["Originating bank fees", formatted(f, "bank_fees")],
        ["Correspondent fee", formatted(f, "intermediary_fee")],
        ["Receiving bank fee", formatted(f, "receiving_fee")],
        ["Total cost of sending", formatted(f, "total_cost") ? `${formatted(f, "total_cost")} (${String(f.cost_pct)}%)` : null],
      ]
    : [
        ["You pay", formatted(f, "you_pay")],
        ["Beneficiary receives", formatted(f, "beneficiary_receives")],
        ["Fee", formatted(f, "fee")],
        ["Way of sending", String(f.rail_label ?? transfer.rail)],
      ];
  return (
    <dl className="kv">
      {rows.filter(([, value]) => value).map(([label, value]) => (
        <Fragment key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </Fragment>
      ))}
    </dl>
  );
}

function Steps({ transfer }: { transfer: BankTransfer }) {
  const returned = transfer.status === "RETURNED";
  return (
    <ol className="timeline" aria-label="Where the money is">
      {transfer.steps.map((step) => (
        <li key={step.stage} className={returned ? "bad" : undefined}>
          <strong>{step.bank_name}</strong> <span className="muted">({step.bank})</span>
          <div>{step.summary}</div>
          <div className="when">
            {returned ? "Not completed, returned" : step.done ? "Done" : `Waits about ${step.delay_seconds} seconds`}
          </div>
        </li>
      ))}
    </ol>
  );
}

function Messages({ events }: { events: BankEvent[] }) {
  return (
    <details>
      <summary>Messages and history ({events.length})</summary>
      <ul className="stack">
        {events.map((event, index) => (
          <li key={`${event.at}-${index}`}>
            <span className="when">{new Date(event.at).toLocaleTimeString()}</span>{" "}
            {event.bank_name ? <strong>{event.bank_name}: </strong> : null}
            {event.note}
            {event.message?.fields ? (
              <div className="table-wrap" tabIndex={0} role="region" aria-label={`${event.message.type ?? "Message"} fields`}>
                <table>
                  <caption className="sr-only">Simulated {event.message.type} message</caption>
                  <thead><tr><th scope="col">Tag</th><th scope="col">Field</th><th scope="col">Value</th></tr></thead>
                  <tbody>
                    {event.message.fields.map((field) => (
                      <tr key={field.tag}><td><code>{field.tag}</code></td><td>{field.name}</td><td>{field.value}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Ledger({ journals }: { journals: BankJournal[] }) {
  return (
    <details>
      <summary>Ledger entries, double entry ({journals.length} journals)</summary>
      {journals.map((journal) => (
        <div key={journal.id} className="table-wrap" tabIndex={0} role="region" aria-label={`Journal: ${journal.memo}`}>
          <table>
            <caption>{journal.kind}: {journal.memo}</caption>
            <thead>
              <tr><th scope="col">Side</th><th scope="col">Bank</th><th scope="col">Account</th><th scope="col" className="num">Amount</th></tr>
            </thead>
            <tbody>
              {journal.lines.map((line, index) => (
                <tr key={index}>
                  <td>{line.side === "DEBIT" ? "Debit" : "Credit"}</td>
                  <td>{line.bank}</td>
                  <td>{line.account}</td>
                  <td className="num">{line.amount.formatted}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </details>
  );
}

interface DetailProps {
  transfer: BankTransfer;
  canTransfer: boolean;
  canControl: boolean;
  sandboxCode?: string;
  onChanged: () => void;
}

/** One transfer: the plan, the hops, the messages and the ledger, with the actions the viewer may take. */
export function TransferDetail({ transfer, canTransfer, canControl, sandboxCode, onChanged }: DetailProps) {
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const confirmKey = useIdempotencyKey(`confirm|${transfer.id}`);
  const cancelKey = useIdempotencyKey(`cancel|${transfer.id}`);
  const pending = transfer.status === "PENDING_CONFIRMATION";

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
      onChanged();
    }
  }

  const confirm = (proof: string) => {
    setAsking(false);
    return run(() => post(`/bank/transfers/${transfer.id}/confirm`, undefined, { idempotencyKey: confirmKey, mfaProof: proof }));
  };

  return (
    <article className="card accent" aria-labelledby={`transfer-${transfer.id}`}>
      <div className="row between">
        <h3 id={`transfer-${transfer.id}`}>
          {transfer.debit.formatted} to {transfer.destination.holder}
        </h3>
        <BankStatusBadge status={transfer.status} />
      </div>
      <p className="small muted">
        {transfer.kind === "INTERNATIONAL" ? "International (SWIFT via a correspondent)" : "National"} · from{" "}
        {transfer.source.bank_name} to {transfer.destination.bank_name} · reference {transfer.reference}
        {transfer.uetr ? <> · UETR <code>{transfer.uetr}</code></> : null}
      </p>
      <ErrorNotice error={error} />
      {transfer.status === "RETURNED" || transfer.status === "CANCELLED" ? (
        <p className="small muted">These were the planned figures. Nothing was charged.</p>
      ) : null}
      <Figures transfer={transfer} />
      {transfer.failure_reason ? <Notice tone="danger" title="Returned">{transfer.failure_reason}</Notice> : null}
      {pending && transfer.blockers.length > 0 ? (
        <Notice tone="warn" title="This cannot be confirmed yet">
          <ul>{transfer.blockers.map((b) => <li key={b.code}>{b.message}</li>)}</ul>
        </Notice>
      ) : null}
      <Steps transfer={transfer} />
      {transfer.events ? <Messages events={transfer.events} /> : null}
      {transfer.journals && transfer.journals.length > 0 ? <Ledger journals={transfer.journals} /> : null}
      <div className="row">
        {pending && canTransfer ? (
          <>
            <button type="button" className="btn primary" disabled={busy || transfer.blockers.length > 0} onClick={() => setAsking(true)}>
              Confirm with MFA
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => void run(() => post(`/bank/transfers/${transfer.id}/cancel`, undefined, { idempotencyKey: cancelKey }))}>
              Cancel this transfer
            </button>
          </>
        ) : null}
        {isOpen(transfer.status) && canControl ? (
          <>
            <button type="button" className="btn small" disabled={busy} onClick={() => void run(() => post(`/bank/transfers/${transfer.id}/sandbox-step`, { outcome: "advance" }))}>
              Run next hop now
            </button>
            <button type="button" className="btn small danger" disabled={busy} onClick={() => void run(() => post(`/bank/transfers/${transfer.id}/sandbox-step`, { outcome: "fail" }))}>
              Make it fail
            </button>
          </>
        ) : null}
      </div>
      <p className="small muted">{transfer.note}</p>
      {asking ? (
        <MfaDialog
          title="Confirm this transfer"
          scope="confirm_bank_transfer"
          subjectId={transfer.id}
          sandboxCode={sandboxCode}
          onProof={(proof) => void confirm(proof)}
          onCancel={() => setAsking(false)}
        />
      ) : null}
    </article>
  );
}

/** Do the books balance, and does every nostro agree with the liability the other bank keeps? */
export function NetworkCard({ network }: { network: BankNetwork }) {
  if (!network.ready) {
    return (
      <Notice tone="warn" title="The bank network is not set up">
        Run <code>python -m app.scripts.seed</code> (in Docker: <code>docker compose exec backend python -m app.scripts.seed</code>).
      </Notice>
    );
  }
  const totals = Object.entries(network.trial_balance ?? {});
  return (
    <section className="card" aria-labelledby="books-title">
      <div className="row between">
        <h2 id="books-title">Do the books balance?</h2>
        <Badge tone={network.all_ok ? "ok" : "danger"}>{network.all_ok ? "All books balance" : "Mismatch found"}</Badge>
      </div>
      <p className="muted">
        Every transfer is double entry: for each currency the debits equal the credits, and each nostro
        account equals the liability the other bank keeps for it. This is checked from the ledger on
        every refresh. The banks are invented.
      </p>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Trial balance by currency">
        <table>
          <caption className="sr-only">Total debits and credits by currency</caption>
          <thead>
            <tr><th scope="col">Currency</th><th scope="col" className="num">Debits (minor units)</th><th scope="col" className="num">Credits (minor units)</th><th scope="col">Balanced</th></tr>
          </thead>
          <tbody>
            {totals.map(([currency, t]) => (
              <tr key={currency}>
                <td>{currency}</td>
                <td className="num">{t.debits.toLocaleString("en-US")}</td>
                <td className="num">{t.credits.toLocaleString("en-US")}</td>
                <td>{t.balanced ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Nostro and reserve accounts against their mirror ({network.mirror_accounts?.length ?? 0})</summary>
        <div className="table-wrap" tabIndex={0} role="region" aria-label="Mirror accounts">
          <table>
            <caption className="sr-only">Each bank&apos;s account at another institution and whether it agrees</caption>
            <thead>
              <tr><th scope="col">Held by</th><th scope="col">At</th><th scope="col">Kind</th><th scope="col" className="num">Balance</th><th scope="col">Agrees</th></tr>
            </thead>
            <tbody>
              {(network.mirror_accounts ?? []).map((m, index) => (
                <tr key={index} className={m.reconciled ? undefined : "fail"}>
                  <td>{m.holder_bank_name}</td>
                  <td>{m.other_name}</td>
                  <td>{m.kind === "NOSTRO" ? "Nostro" : "Reserve"}</td>
                  <td className="num">{m.balance.formatted}</td>
                  <td>{m.reconciled ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
