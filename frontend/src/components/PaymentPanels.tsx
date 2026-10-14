import type { Mt103Preview, Payment, Summary, Tracker } from "../api/types";
import { formatDate, formatDateTime } from "../lib/format";
import { Countdown } from "./Countdown";
import { Badge, Notice, StateBadge } from "./Ui";

/** The facts a human must read before approving. Its hash binds the approval to them. */
export function SummaryCard({ payment }: { payment: Payment }) {
  const summary: Summary | null = payment.summary ?? payment.summary_preview;
  const frozen = payment.summary !== null;
  if (!summary) return null;
  const open = ["QUOTED", "PENDING_APPROVAL", "DRAFT"].includes(payment.state);
  return (
    <section className="card" aria-labelledby="summary-title">
      <div className="row between">
        <h2 id="summary-title">{frozen ? "Approval summary" : "Preview of the approval summary"}</h2>
        {open && payment.quote_status === "ACTIVE" ? <Countdown expiresAt={payment.quote_expires_at} /> : null}
        {open && payment.quote_status === "EXPIRED" ? <Badge tone="danger">Quote expired</Badge> : null}
      </div>
      {summary.shortfall_foreign_minor > 0 ? (
        <Notice tone="danger" title="Shortfall risk">
          Fees will be taken from the amount, so the university may receive less than the invoice. A charge code of OUR avoids this.
        </Notice>
      ) : null}
      <dl className="kv">
        <dt>Recipient</dt><dd>{summary.recipient}</dd>
        <dt>Provider</dt><dd>{summary.provider_name}</dd>
        <dt>Reference</dt><dd>{summary.reference}</dd>
        <dt>Beneficiary receives</dt><dd><strong>{summary.display.beneficiary_receives}</strong></dd>
        <dt>Rate</dt><dd>{summary.rate} BDT per {summary.beneficiary_receives.currency}</dd>
        <dt>Charge code</dt><dd>{summary.charge_code}</dd>
        <dt>Total cost</dt><dd>{summary.display.total_cost} ({summary.display.cost_pct})</dd>
        <dt>You pay</dt><dd><strong>{summary.display.parent_pays}</strong></dd>
        <dt>Latest send date</dt><dd>{formatDate(summary.latest_send_date)}</dd>
        <dt>Quote expires</dt><dd>{formatDateTime(summary.quote_expires_at)}</dd>
      </dl>
      <p className="small muted">{summary.disclaimer} Indicative. Confirm with your AD bank.</p>
    </section>
  );
}

/** Payment instruction preview: shows the originator and beneficiary data (the travel rule). */
export function Mt103Card({ preview }: { preview: Mt103Preview }) {
  return (
    <section className="card" aria-labelledby="mt103-title">
      <div className="row between">
        <h2 id="mt103-title">Payment instruction preview</h2>
        <Badge tone="neutral">{preview.format} - simulated</Badge>
      </div>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Instruction preview fields table">
        <table>
          <thead>
            <tr><th scope="col">Tag</th><th scope="col">Field</th><th scope="col">Value</th><th scope="col">Note</th></tr>
          </thead>
          <tbody>
            {preview.fields.map((f) => (
              <tr key={f.tag}>
                <td><code>{f.tag}</code></td>
                <td>{f.name}</td>
                <td className="mono">{f.value}</td>
                <td className="small muted">{f.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small">
        ISO 20022 equivalent: <code>ChrgBr = {preview.pacs008.ChrgBr}</code>, <code>RmtInf = {preview.pacs008.RmtInf}</code>.
      </p>
      <ul className="small muted">
        {preview.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </section>
  );
}

/** Status timeline with the UETR. */
export function TrackerCard({ tracker }: { tracker: Tracker }) {
  return (
    <section className="card" aria-labelledby="tracker-title">
      <div className="row between">
        <h2 id="tracker-title">Status tracker</h2>
        <StateBadge state={tracker.state} />
      </div>
      <dl className="kv">
        <dt>UETR</dt><dd className="mono">{tracker.uetr ?? "Assigned when the payment is submitted"}</dd>
        <dt>Host-country rail</dt><dd>{tracker.host_rail}</dd>
      </dl>
      <ol className="timeline" aria-label="Payment timeline">
        {tracker.timeline.map((step, index) => (
          <li key={`${step.state}-${index}`} className={step.state === "FAILED" || step.state === "REJECTED" ? "bad" : undefined}>
            <StateBadge state={step.state} />
            <div className="when">{formatDateTime(step.at)} by {step.actor_type}</div>
            {step.note ? <div>{step.note}</div> : null}
          </li>
        ))}
      </ol>
      <p className="small muted">Simulated. No real bank or SWIFT network is contacted.</p>
    </section>
  );
}
